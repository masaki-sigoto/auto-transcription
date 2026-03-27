/**
 * オフラインデータベース（SQLite）
 */

import * as SQLite from 'expo-sqlite';

let db: SQLite.SQLiteDatabase | null = null;

export async function initDatabase(): Promise<void> {
  db = await SQLite.openDatabaseAsync('transcription.db');

  // テーブル作成
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS transcriptions (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      status TEXT NOT NULL,
      audio_path TEXT,
      audio_duration_sec REAL,
      full_text TEXT,
      language TEXT DEFAULT 'ja',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      synced INTEGER DEFAULT 0,
      server_id TEXT
    );

    CREATE TABLE IF NOT EXISTS segments (
      id TEXT PRIMARY KEY,
      transcription_id TEXT NOT NULL,
      start_time_ms INTEGER NOT NULL,
      end_time_ms INTEGER NOT NULL,
      text TEXT NOT NULL,
      speaker_label TEXT,
      confidence REAL,
      FOREIGN KEY (transcription_id) REFERENCES transcriptions (id)
    );

    CREATE TABLE IF NOT EXISTS pending_uploads (
      id TEXT PRIMARY KEY,
      transcription_id TEXT NOT NULL,
      audio_path TEXT NOT NULL,
      created_at TEXT NOT NULL,
      attempts INTEGER DEFAULT 0,
      last_error TEXT,
      FOREIGN KEY (transcription_id) REFERENCES transcriptions (id)
    );

    CREATE TABLE IF NOT EXISTS offline_recordings (
      id TEXT PRIMARY KEY,
      audio_path TEXT NOT NULL,
      duration_sec REAL,
      title TEXT,
      created_at TEXT NOT NULL,
      processed INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_transcriptions_synced ON transcriptions (synced);
    CREATE INDEX IF NOT EXISTS idx_segments_transcription ON segments (transcription_id);
  `);
}

export function getDatabase(): SQLite.SQLiteDatabase {
  if (!db) {
    throw new Error('Database not initialized');
  }
  return db;
}

// === Transcription CRUD ===

export interface LocalTranscription {
  id: string;
  title: string;
  status: string;
  audio_path?: string;
  audio_duration_sec?: number;
  full_text?: string;
  language: string;
  created_at: string;
  updated_at: string;
  synced: boolean;
  server_id?: string;
}

export async function saveTranscription(transcription: LocalTranscription): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    `INSERT OR REPLACE INTO transcriptions
    (id, title, status, audio_path, audio_duration_sec, full_text, language, created_at, updated_at, synced, server_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      transcription.id,
      transcription.title,
      transcription.status,
      transcription.audio_path || null,
      transcription.audio_duration_sec || null,
      transcription.full_text || null,
      transcription.language,
      transcription.created_at,
      transcription.updated_at,
      transcription.synced ? 1 : 0,
      transcription.server_id || null,
    ]
  );
}

export async function getTranscriptions(): Promise<LocalTranscription[]> {
  const db = getDatabase();

  const results = await db.getAllAsync<any>(
    'SELECT * FROM transcriptions ORDER BY created_at DESC'
  );

  return results.map((row) => ({
    ...row,
    synced: row.synced === 1,
  }));
}

export async function getTranscription(id: string): Promise<LocalTranscription | null> {
  const db = getDatabase();

  const result = await db.getFirstAsync<any>(
    'SELECT * FROM transcriptions WHERE id = ?',
    [id]
  );

  if (!result) return null;

  return {
    ...result,
    synced: result.synced === 1,
  };
}

export async function deleteTranscription(id: string): Promise<void> {
  const db = getDatabase();

  await db.runAsync('DELETE FROM segments WHERE transcription_id = ?', [id]);
  await db.runAsync('DELETE FROM transcriptions WHERE id = ?', [id]);
}

export async function getUnsyncedTranscriptions(): Promise<LocalTranscription[]> {
  const db = getDatabase();

  const results = await db.getAllAsync<any>(
    'SELECT * FROM transcriptions WHERE synced = 0'
  );

  return results.map((row) => ({
    ...row,
    synced: false,
  }));
}

export async function markTranscriptionSynced(id: string, serverId: string): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    'UPDATE transcriptions SET synced = 1, server_id = ? WHERE id = ?',
    [serverId, id]
  );
}

// === Segments ===

export interface LocalSegment {
  id: string;
  transcription_id: string;
  start_time_ms: number;
  end_time_ms: number;
  text: string;
  speaker_label?: string;
  confidence?: number;
}

export async function saveSegments(segments: LocalSegment[]): Promise<void> {
  const db = getDatabase();

  for (const segment of segments) {
    await db.runAsync(
      `INSERT OR REPLACE INTO segments
      (id, transcription_id, start_time_ms, end_time_ms, text, speaker_label, confidence)
      VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        segment.id,
        segment.transcription_id,
        segment.start_time_ms,
        segment.end_time_ms,
        segment.text,
        segment.speaker_label || null,
        segment.confidence || null,
      ]
    );
  }
}

export async function getSegments(transcriptionId: string): Promise<LocalSegment[]> {
  const db = getDatabase();

  return await db.getAllAsync<LocalSegment>(
    'SELECT * FROM segments WHERE transcription_id = ? ORDER BY start_time_ms',
    [transcriptionId]
  );
}

// === Offline Recordings ===

export interface OfflineRecording {
  id: string;
  audio_path: string;
  duration_sec?: number;
  title?: string;
  created_at: string;
  processed: boolean;
}

export async function saveOfflineRecording(recording: OfflineRecording): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    `INSERT INTO offline_recordings (id, audio_path, duration_sec, title, created_at, processed)
    VALUES (?, ?, ?, ?, ?, ?)`,
    [
      recording.id,
      recording.audio_path,
      recording.duration_sec || null,
      recording.title || null,
      recording.created_at,
      recording.processed ? 1 : 0,
    ]
  );
}

export async function getOfflineRecordings(): Promise<OfflineRecording[]> {
  const db = getDatabase();

  const results = await db.getAllAsync<any>(
    'SELECT * FROM offline_recordings WHERE processed = 0 ORDER BY created_at DESC'
  );

  return results.map((row) => ({
    ...row,
    processed: row.processed === 1,
  }));
}

export async function markRecordingProcessed(id: string): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    'UPDATE offline_recordings SET processed = 1 WHERE id = ?',
    [id]
  );
}

// === Pending Uploads ===

export interface PendingUpload {
  id: string;
  transcription_id: string;
  audio_path: string;
  created_at: string;
  attempts: number;
  last_error?: string;
}

export async function addPendingUpload(upload: PendingUpload): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    `INSERT INTO pending_uploads (id, transcription_id, audio_path, created_at, attempts, last_error)
    VALUES (?, ?, ?, ?, ?, ?)`,
    [
      upload.id,
      upload.transcription_id,
      upload.audio_path,
      upload.created_at,
      upload.attempts,
      upload.last_error || null,
    ]
  );
}

export async function getPendingUploads(): Promise<PendingUpload[]> {
  const db = getDatabase();

  return await db.getAllAsync<PendingUpload>(
    'SELECT * FROM pending_uploads ORDER BY created_at'
  );
}

export async function removePendingUpload(id: string): Promise<void> {
  const db = getDatabase();

  await db.runAsync('DELETE FROM pending_uploads WHERE id = ?', [id]);
}

export async function updatePendingUploadError(id: string, error: string): Promise<void> {
  const db = getDatabase();

  await db.runAsync(
    'UPDATE pending_uploads SET attempts = attempts + 1, last_error = ? WHERE id = ?',
    [error, id]
  );
}
