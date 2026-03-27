export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  plan: 'free' | 'pro' | 'enterprise';
  usage_minutes_month: number;
  created_at: string;
  updated_at: string;
}

export interface Speaker {
  id: string;
  label: string;
  color: string | null;
}

export interface Segment {
  id: string;
  start_time_ms: number;
  end_time_ms: number;
  text: string;
  speaker_id: string | null;
  confidence: number | null;
  is_edited: boolean;
}

export interface Transcription {
  id: string;
  user_id: string;
  title: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  audio_url: string;
  audio_duration_sec: number | null;
  language: string;
  engine: 'reazon' | 'whisper' | 'hybrid';
  enable_diarization: boolean;
  enable_llm_correction: boolean;
  summary: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptionDetail extends Transcription {
  segments: Segment[];
  speakers: Speaker[];
}

export interface TranscriptionListResponse {
  items: Transcription[];
  total: number;
  page: number;
  per_page: number;
}

export interface TranscriptionOptions {
  enable_diarization: boolean;
  enable_llm_correction: boolean;
  remove_filler_words: boolean;
  custom_vocabulary: string[];
}

export interface CreateTranscriptionRequest {
  audio_url: string;
  title?: string;
  language: string;
  engine: 'reazon' | 'whisper' | 'hybrid';
  options: TranscriptionOptions;
}

export interface TranscriptionJobResponse {
  id: string;
  status: string;
  estimated_completion_sec: number | null;
}

export interface ExportRequest {
  format: 'txt' | 'srt' | 'vtt' | 'docx' | 'json';
}

export interface ExportResponse {
  download_url: string;
  expires_at: string;
}

export interface Summary {
  summary: string;
  topics: string[];
  decisions: string[];
  action_items: string[];
}
