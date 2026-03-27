import { create } from 'zustand';
import { authApi, type AuthUser } from '../lib/api';

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;

  // Actions
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  loginWithGoogle: () => void;
  loginWithGithub: () => void;
  logout: () => Promise<void>;
  updateUser: (updates: { name?: string; avatar_url?: string }) => Promise<void>;
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  error: null,

  initialize: async () => {
    try {
      const accessToken = localStorage.getItem('access_token');

      if (!accessToken) {
        set({ user: null, isAuthenticated: false, isLoading: false });
        return;
      }

      // トークンがある場合はユーザー情報を取得
      const user = await authApi.getMe();
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error) {
      // トークンが無効な場合はクリア
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const tokens = await authApi.login(email, password);

      // トークンを保存
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);

      // ユーザー情報を取得
      const user = await authApi.getMe();
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error: any) {
      const message = error.response?.data?.detail || 'ログインに失敗しました';
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  register: async (email, password, name) => {
    set({ isLoading: true, error: null });
    try {
      const tokens = await authApi.register(email, password, name);

      // トークンを保存
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);

      // ユーザー情報を取得
      const user = await authApi.getMe();
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error: any) {
      const message = error.response?.data?.detail || '登録に失敗しました';
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  loginWithGoogle: () => {
    // Google OAuthページにリダイレクト
    window.location.href = authApi.getGoogleAuthUrl();
  },

  loginWithGithub: () => {
    // GitHub OAuthページにリダイレクト
    window.location.href = authApi.getGithubAuthUrl();
  },

  logout: async () => {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        await authApi.logout(refreshToken);
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // ローカルストレージをクリア
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      set({ user: null, isAuthenticated: false });
    }
  },

  updateUser: async (updates) => {
    try {
      const user = await authApi.updateMe(updates);
      set({ user });
    } catch (error: any) {
      const message = error.response?.data?.detail || '更新に失敗しました';
      set({ error: message });
      throw error;
    }
  },

  changePassword: async (oldPassword, newPassword) => {
    try {
      await authApi.changePassword(oldPassword, newPassword);
    } catch (error: any) {
      const message = error.response?.data?.detail || 'パスワード変更に失敗しました';
      set({ error: message });
      throw error;
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));

// OAuthコールバック処理用のヘルパー関数
export const handleOAuthCallback = async (
  accessToken: string,
  refreshToken: string
): Promise<AuthUser> => {
  // トークンを保存
  localStorage.setItem('access_token', accessToken);
  localStorage.setItem('refresh_token', refreshToken);

  // ユーザー情報を取得
  const user = await authApi.getMe();

  // Storeを更新
  useAuthStore.setState({
    user,
    isAuthenticated: true,
    isLoading: false,
  });

  return user;
};
