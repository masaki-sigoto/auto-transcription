import axios, { AxiosError } from 'axios';
import type {
  Transcription,
  TranscriptionDetail,
  TranscriptionListResponse,
  CreateTranscriptionRequest,
  TranscriptionJobResponse,
  ExportRequest,
  ExportResponse,
  Summary,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// リクエストインターセプター（認証トークン付与）
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// レスポンスインターセプター（トークンリフレッシュ）
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as any;

    // 401エラーでリフレッシュトークンがある場合
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);

          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
          return api(originalRequest);
        } catch (refreshError) {
          // リフレッシュ失敗時はログアウト
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      }
    }

    return Promise.reject(error);
  }
);

// Auth API
export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  plan: string;
  is_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export const authApi = {
  // ユーザー登録
  register: async (email: string, password: string, name?: string): Promise<TokenResponse> => {
    const { data } = await api.post('/auth/register', { email, password, name });
    return data;
  },

  // ログイン
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const { data } = await api.post('/auth/login', { email, password });
    return data;
  },

  // ログアウト
  logout: async (refreshToken: string): Promise<void> => {
    await api.post('/auth/logout', { refresh_token: refreshToken });
  },

  // 全デバイスからログアウト
  logoutAll: async (): Promise<void> => {
    await api.post('/auth/logout-all');
  },

  // トークンリフレッシュ
  refresh: async (refreshToken: string): Promise<TokenResponse> => {
    const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken });
    return data;
  },

  // 現在のユーザー情報取得
  getMe: async (): Promise<AuthUser> => {
    const { data } = await api.get('/auth/me');
    return data;
  },

  // ユーザー情報更新
  updateMe: async (updates: { name?: string; avatar_url?: string }): Promise<AuthUser> => {
    const { data } = await api.patch('/auth/me', updates);
    return data;
  },

  // パスワード変更
  changePassword: async (oldPassword: string, newPassword: string): Promise<void> => {
    await api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
  },

  // Google OAuth URL
  getGoogleAuthUrl: (): string => {
    return `${API_BASE_URL}/auth/google`;
  },

  // GitHub OAuth URL
  getGithubAuthUrl: (): string => {
    return `${API_BASE_URL}/auth/github`;
  },
};

// Transcription API
export const transcriptionApi = {
  // 一覧取得
  list: async (page = 1, perPage = 20): Promise<TranscriptionListResponse> => {
    const { data } = await api.get('/transcriptions', {
      params: { page, per_page: perPage },
    });
    return data;
  },

  // 詳細取得
  get: async (id: string): Promise<TranscriptionDetail> => {
    const { data } = await api.get(`/transcriptions/${id}`);
    return data;
  },

  // 新規作成
  create: async (request: CreateTranscriptionRequest): Promise<TranscriptionJobResponse> => {
    const { data } = await api.post('/transcriptions', request);
    return data;
  },

  // 更新
  update: async (id: string, updates: { title?: string }): Promise<Transcription> => {
    const { data } = await api.patch(`/transcriptions/${id}`, updates);
    return data;
  },

  // 削除
  delete: async (id: string): Promise<void> => {
    await api.delete(`/transcriptions/${id}`);
  },

  // セグメント更新
  updateSegment: async (
    segmentId: string,
    updates: { text?: string; speaker_id?: string }
  ): Promise<void> => {
    await api.put(`/segments/${segmentId}`, updates);
  },

  // エクスポート
  export: async (id: string, request: ExportRequest): Promise<ExportResponse> => {
    const { data } = await api.post(`/transcriptions/${id}/export`, request);
    return data;
  },

  // AI要約
  summarize: async (id: string): Promise<Summary> => {
    const { data } = await api.post(`/transcriptions/${id}/summarize`);
    return data;
  },
};

// Upload API
export const uploadApi = {
  // 署名付きアップロードURL取得（S3使用時）
  getPresignedUrl: async (fileExtension: string): Promise<{ upload_url: string; file_key: string }> => {
    const { data } = await api.post('/upload/presigned', null, {
      params: { file_extension: fileExtension },
    });
    return data;
  },

  // ファイルアップロード（S3使用時）
  uploadFile: async (url: string, file: File): Promise<void> => {
    await axios.put(url, file, {
      headers: {
        'Content-Type': file.type,
      },
    });
  },

  // 直接アップロード（ローカルストレージ使用時）
  directUpload: async (file: File): Promise<{ file_key: string; audio_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/upload/direct', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },
};
