/**
 * オフライン文字起こしサービス
 * デバイス上での音声認識処理
 */

import * as FileSystem from 'expo-file-system';
import { Audio } from 'expo-av';
import {
  saveTranscription,
  saveSegments,
  LocalTranscription,
  LocalSegment,
  saveOfflineRecording,
  markRecordingProcessed,
} from './database';

// 録音設定
const RECORDING_OPTIONS = {
  android: {
    extension: '.m4a',
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 44100,
    numberOfChannels: 2,
    bitRate: 128000,
  },
  ios: {
    extension: '.m4a',
    outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
    audioQuality: Audio.IOSAudioQuality.HIGH,
    sampleRate: 44100,
    numberOfChannels: 2,
    bitRate: 128000,
  },
  web: {
    mimeType: 'audio/webm',
    bitsPerSecond: 128000,
  },
};

export class OfflineRecorder {
  private recording: Audio.Recording | null = null;
  private isRecording = false;

  async startRecording(): Promise<void> {
    try {
      // パーミッション確認
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        throw new Error('マイクのアクセス許可が必要です');
      }

      // オーディオモード設定
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      // 録音開始
      const { recording } = await Audio.Recording.createAsync(RECORDING_OPTIONS);
      this.recording = recording;
      this.isRecording = true;
    } catch (error) {
      console.error('Failed to start recording:', error);
      throw error;
    }
  }

  async stopRecording(): Promise<{
    uri: string;
    duration: number;
  }> {
    if (!this.recording) {
      throw new Error('録音が開始されていません');
    }

    try {
      await this.recording.stopAndUnloadAsync();
      const uri = this.recording.getURI();
      const status = await this.recording.getStatusAsync();

      this.recording = null;
      this.isRecording = false;

      if (!uri) {
        throw new Error('録音ファイルの保存に失敗しました');
      }

      return {
        uri,
        duration: (status.durationMillis || 0) / 1000,
      };
    } catch (error) {
      console.error('Failed to stop recording:', error);
      throw error;
    }
  }

  async pauseRecording(): Promise<void> {
    if (this.recording) {
      await this.recording.pauseAsync();
    }
  }

  async resumeRecording(): Promise<void> {
    if (this.recording) {
      await this.recording.startAsync();
    }
  }

  getIsRecording(): boolean {
    return this.isRecording;
  }
}

/**
 * オフライン文字起こし処理
 * 注: 実際のオフライン文字起こしには、
 * - Whisper.cpp などのローカルモデル
 * - または expo-speech-recognition を使用
 */
export async function processOfflineTranscription(
  audioUri: string,
  title: string
): Promise<LocalTranscription> {
  const id = generateId();
  const now = new Date().toISOString();

  // ファイル情報を取得
  const fileInfo = await FileSystem.getInfoAsync(audioUri);

  // ローカルストレージにコピー
  const localPath = `${FileSystem.documentDirectory}recordings/${id}.m4a`;
  await FileSystem.makeDirectoryAsync(
    `${FileSystem.documentDirectory}recordings`,
    { intermediates: true }
  );
  await FileSystem.copyAsync({ from: audioUri, to: localPath });

  // 文字起こしを作成（処理待ち状態）
  const transcription: LocalTranscription = {
    id,
    title,
    status: 'pending',
    audio_path: localPath,
    language: 'ja',
    created_at: now,
    updated_at: now,
    synced: false,
  };

  await saveTranscription(transcription);

  // オフライン録音として登録（後でオンライン時に処理）
  await saveOfflineRecording({
    id: generateId(),
    audio_path: localPath,
    title,
    created_at: now,
    processed: false,
  });

  return transcription;
}

/**
 * シンプルな音声認識（デバイスの音声認識API使用）
 * 注: これはリアルタイム認識用で、長い音声には向かない
 */
export async function transcribeWithDeviceRecognition(
  onResult: (text: string, isFinal: boolean) => void,
  language: string = 'ja-JP'
): Promise<{
  start: () => Promise<void>;
  stop: () => Promise<void>;
}> {
  // expo-speech-recognition を使用する場合の実装
  // 現時点では完全なオフライン文字起こしは限定的

  let isListening = false;

  return {
    start: async () => {
      // デバイスの音声認識を開始
      // 実際の実装は expo-speech-recognition パッケージに依存
      isListening = true;
      console.log('Speech recognition started');
    },
    stop: async () => {
      isListening = false;
      console.log('Speech recognition stopped');
    },
  };
}

/**
 * 音声ファイルを分析して基本情報を取得
 */
export async function analyzeAudioFile(uri: string): Promise<{
  duration: number;
  size: number;
}> {
  const fileInfo = await FileSystem.getInfoAsync(uri, { size: true });

  // 音声の長さを取得
  const sound = new Audio.Sound();
  await sound.loadAsync({ uri });
  const status = await sound.getStatusAsync();
  await sound.unloadAsync();

  return {
    duration: status.isLoaded ? (status.durationMillis || 0) / 1000 : 0,
    size: fileInfo.exists && 'size' in fileInfo ? fileInfo.size : 0,
  };
}

/**
 * 音声ファイルを圧縮
 */
export async function compressAudio(
  inputUri: string,
  quality: 'low' | 'medium' | 'high' = 'medium'
): Promise<string> {
  // 実際の圧縮処理は ffmpeg-kit などを使用
  // ここではシンプルにコピーのみ
  const outputPath = inputUri.replace('.m4a', '_compressed.m4a');
  await FileSystem.copyAsync({ from: inputUri, to: outputPath });
  return outputPath;
}

/**
 * 録音ファイルを削除
 */
export async function deleteRecordingFile(uri: string): Promise<void> {
  try {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  } catch (error) {
    console.error('Failed to delete recording file:', error);
  }
}

/**
 * ストレージ使用量を取得
 */
export async function getStorageUsage(): Promise<{
  used: number;
  available: number;
}> {
  const recordingsDir = `${FileSystem.documentDirectory}recordings`;

  try {
    const dirInfo = await FileSystem.readDirectoryAsync(recordingsDir);
    let totalSize = 0;

    for (const file of dirInfo) {
      const fileInfo = await FileSystem.getInfoAsync(
        `${recordingsDir}/${file}`,
        { size: true }
      );
      if (fileInfo.exists && 'size' in fileInfo) {
        totalSize += fileInfo.size;
      }
    }

    // 利用可能な容量は概算
    const available = 1024 * 1024 * 1024; // 1GB（実際の値はデバイスAPI使用）

    return { used: totalSize, available };
  } catch {
    return { used: 0, available: 1024 * 1024 * 1024 };
  }
}

// ユーティリティ
function generateId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
