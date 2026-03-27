/**
 * データ同期サービス
 * オフラインデータをサーバーと同期
 */

import * as FileSystem from 'expo-file-system';
import NetInfo from '@react-native-community/netinfo';
import {
  getUnsyncedTranscriptions,
  markTranscriptionSynced,
  getPendingUploads,
  removePendingUpload,
  updatePendingUploadError,
  getOfflineRecordings,
  markRecordingProcessed,
  saveTranscription,
  saveSegments,
  LocalTranscription,
} from './database';
import { getApiUrl, getAuthToken } from './api';

export interface SyncStatus {
  isSyncing: boolean;
  pendingCount: number;
  lastSyncAt: string | null;
  error: string | null;
}

let syncStatus: SyncStatus = {
  isSyncing: false,
  pendingCount: 0,
  lastSyncAt: null,
  error: null,
};

let syncListeners: ((status: SyncStatus) => void)[] = [];

export function subscribeSyncStatus(
  listener: (status: SyncStatus) => void
): () => void {
  syncListeners.push(listener);
  listener(syncStatus);
  return () => {
    syncListeners = syncListeners.filter((l) => l !== listener);
  };
}

function updateSyncStatus(updates: Partial<SyncStatus>): void {
  syncStatus = { ...syncStatus, ...updates };
  syncListeners.forEach((listener) => listener(syncStatus));
}

/**
 * ネットワーク状態を監視して自動同期
 */
export function startAutoSync(): () => void {
  const unsubscribe = NetInfo.addEventListener((state) => {
    if (state.isConnected && state.isInternetReachable) {
      // オンラインになったら同期開始
      syncAll();
    }
  });

  // 定期同期（5分ごと）
  const interval = setInterval(() => {
    syncAll();
  }, 5 * 60 * 1000);

  return () => {
    unsubscribe();
    clearInterval(interval);
  };
}

/**
 * すべてのデータを同期
 */
export async function syncAll(): Promise<void> {
  if (syncStatus.isSyncing) return;

  // ネットワーク確認
  const netState = await NetInfo.fetch();
  if (!netState.isConnected || !netState.isInternetReachable) {
    return;
  }

  updateSyncStatus({ isSyncing: true, error: null });

  try {
    // 1. 未同期の文字起こしをアップロード
    await uploadUnsyncedTranscriptions();

    // 2. 保留中のアップロードを処理
    await processPendingUploads();

    // 3. オフライン録音を処理
    await processOfflineRecordings();

    // 4. サーバーから最新データを取得
    await fetchLatestFromServer();

    updateSyncStatus({
      isSyncing: false,
      lastSyncAt: new Date().toISOString(),
      pendingCount: 0,
    });
  } catch (error) {
    console.error('Sync failed:', error);
    updateSyncStatus({
      isSyncing: false,
      error: error instanceof Error ? error.message : 'Sync failed',
    });
  }
}

/**
 * 未同期の文字起こしをアップロード
 */
async function uploadUnsyncedTranscriptions(): Promise<void> {
  const unsynced = await getUnsyncedTranscriptions();
  const apiUrl = getApiUrl();
  const token = await getAuthToken();

  for (const transcription of unsynced) {
    try {
      // メタデータをアップロード
      const response = await fetch(`${apiUrl}/api/v1/transcriptions/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          local_id: transcription.id,
          title: transcription.title,
          status: transcription.status,
          audio_duration_sec: transcription.audio_duration_sec,
          full_text: transcription.full_text,
          language: transcription.language,
          created_at: transcription.created_at,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        await markTranscriptionSynced(transcription.id, data.id);
      }
    } catch (error) {
      console.error(`Failed to sync transcription ${transcription.id}:`, error);
    }
  }
}

/**
 * 保留中のアップロードを処理
 */
async function processPendingUploads(): Promise<void> {
  const pending = await getPendingUploads();
  const apiUrl = getApiUrl();
  const token = await getAuthToken();

  for (const upload of pending) {
    // 最大3回まで再試行
    if (upload.attempts >= 3) {
      continue;
    }

    try {
      // ファイルをアップロード
      const uploadResult = await FileSystem.uploadAsync(
        `${apiUrl}/api/v1/upload/audio`,
        upload.audio_path,
        {
          uploadType: FileSystem.FileSystemUploadType.MULTIPART,
          fieldName: 'file',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          parameters: {
            transcription_id: upload.transcription_id,
          },
        }
      );

      if (uploadResult.status === 200) {
        await removePendingUpload(upload.id);
      } else {
        throw new Error(`Upload failed with status ${uploadResult.status}`);
      }
    } catch (error) {
      await updatePendingUploadError(
        upload.id,
        error instanceof Error ? error.message : 'Unknown error'
      );
    }
  }
}

/**
 * オフライン録音を処理（サーバーで文字起こし）
 */
async function processOfflineRecordings(): Promise<void> {
  const recordings = await getOfflineRecordings();
  const apiUrl = getApiUrl();
  const token = await getAuthToken();

  for (const recording of recordings) {
    try {
      // 音声ファイルをアップロードして文字起こし
      const uploadResult = await FileSystem.uploadAsync(
        `${apiUrl}/api/v1/upload/transcribe`,
        recording.audio_path,
        {
          uploadType: FileSystem.FileSystemUploadType.MULTIPART,
          fieldName: 'file',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          parameters: {
            title: recording.title || 'オフライン録音',
            language: 'ja',
          },
        }
      );

      if (uploadResult.status === 200 || uploadResult.status === 202) {
        await markRecordingProcessed(recording.id);
      }
    } catch (error) {
      console.error(`Failed to process recording ${recording.id}:`, error);
    }
  }
}

/**
 * サーバーから最新データを取得
 */
async function fetchLatestFromServer(): Promise<void> {
  const apiUrl = getApiUrl();
  const token = await getAuthToken();

  try {
    const response = await fetch(`${apiUrl}/api/v1/transcriptions?limit=50`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) return;

    const transcriptions = await response.json();

    for (const t of transcriptions) {
      // サーバーからの文字起こしをローカルに保存
      const localTranscription: LocalTranscription = {
        id: t.id,
        title: t.title,
        status: t.status,
        audio_duration_sec: t.audio_duration_sec,
        full_text: t.full_text,
        language: t.language || 'ja',
        created_at: t.created_at,
        updated_at: t.updated_at,
        synced: true,
        server_id: t.id,
      };

      await saveTranscription(localTranscription);

      // セグメントも保存
      if (t.segments) {
        await saveSegments(
          t.segments.map((s: any) => ({
            id: s.id,
            transcription_id: t.id,
            start_time_ms: s.start_time_ms,
            end_time_ms: s.end_time_ms,
            text: s.text,
            speaker_label: s.speaker_label,
            confidence: s.confidence,
          }))
        );
      }
    }
  } catch (error) {
    console.error('Failed to fetch from server:', error);
  }
}

/**
 * 同期状態を取得
 */
export function getSyncStatus(): SyncStatus {
  return syncStatus;
}

/**
 * 保留中のアイテム数を更新
 */
export async function updatePendingCount(): Promise<void> {
  const unsynced = await getUnsyncedTranscriptions();
  const pending = await getPendingUploads();
  const recordings = await getOfflineRecordings();

  updateSyncStatus({
    pendingCount: unsynced.length + pending.length + recordings.length,
  });
}
