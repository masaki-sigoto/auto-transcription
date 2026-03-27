import { useState, useEffect, useCallback } from 'react';
import {
  registerServiceWorker,
  setupInstallPrompt,
  isInstallable,
  showInstallPrompt,
  isInstalledPWA,
  setupOnlineListener,
  requestNotificationPermission,
  offlineStorage,
} from '../lib/pwa';

interface PWAState {
  isOnline: boolean;
  isInstallable: boolean;
  isInstalled: boolean;
  isUpdateAvailable: boolean;
  notificationPermission: NotificationPermission;
  pendingUploadsCount: number;
}

export function usePWA() {
  const [state, setState] = useState<PWAState>({
    isOnline: navigator.onLine,
    isInstallable: false,
    isInstalled: isInstalledPWA(),
    isUpdateAvailable: false,
    notificationPermission: 'default',
    pendingUploadsCount: 0,
  });

  useEffect(() => {
    // Service Workerの登録
    registerServiceWorker();

    // インストールプロンプトのセットアップ
    setupInstallPrompt();

    // オンライン状態の監視
    const cleanup = setupOnlineListener(
      () => setState((s) => ({ ...s, isOnline: true })),
      () => setState((s) => ({ ...s, isOnline: false }))
    );

    // インストール可能イベント
    const handleInstallable = () => {
      setState((s) => ({ ...s, isInstallable: true }));
    };
    window.addEventListener('pwa-installable', handleInstallable);

    // 更新利用可能イベント
    const handleUpdateAvailable = () => {
      setState((s) => ({ ...s, isUpdateAvailable: true }));
    };
    window.addEventListener('sw-update-available', handleUpdateAvailable);

    // 通知権限の確認
    if ('Notification' in window) {
      setState((s) => ({ ...s, notificationPermission: Notification.permission }));
    }

    // 保留中のアップロード数を確認
    offlineStorage.getPendingUploads().then((uploads) => {
      setState((s) => ({ ...s, pendingUploadsCount: uploads.length }));
    });

    return () => {
      cleanup();
      window.removeEventListener('pwa-installable', handleInstallable);
      window.removeEventListener('sw-update-available', handleUpdateAvailable);
    };
  }, []);

  const install = useCallback(async () => {
    const accepted = await showInstallPrompt();
    if (accepted) {
      setState((s) => ({ ...s, isInstallable: false, isInstalled: true }));
    }
    return accepted;
  }, []);

  const requestNotifications = useCallback(async () => {
    const permission = await requestNotificationPermission();
    setState((s) => ({ ...s, notificationPermission: permission }));
    return permission;
  }, []);

  const updateApp = useCallback(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistration().then((registration) => {
        if (registration?.waiting) {
          registration.waiting.postMessage({ type: 'SKIP_WAITING' });
          window.location.reload();
        }
      });
    }
  }, []);

  const refreshPendingCount = useCallback(async () => {
    const uploads = await offlineStorage.getPendingUploads();
    setState((s) => ({ ...s, pendingUploadsCount: uploads.length }));
  }, []);

  return {
    ...state,
    install,
    requestNotifications,
    updateApp,
    refreshPendingCount,
  };
}

// オフラインストレージへのアクセス
export function useOfflineStorage() {
  const saveForOffline = useCallback(async (transcription: any) => {
    await offlineStorage.saveTranscription(transcription);
  }, []);

  const getOfflineTranscription = useCallback(async (id: string) => {
    return offlineStorage.getTranscription(id);
  }, []);

  const getAllOfflineTranscriptions = useCallback(async () => {
    return offlineStorage.getAllTranscriptions();
  }, []);

  const savePendingUpload = useCallback(async (file: File, metadata: Record<string, any>) => {
    return offlineStorage.savePendingUpload(file, metadata);
  }, []);

  return {
    saveForOffline,
    getOfflineTranscription,
    getAllOfflineTranscriptions,
    savePendingUpload,
  };
}
