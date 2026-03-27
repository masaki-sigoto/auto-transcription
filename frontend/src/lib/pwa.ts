// PWA関連のユーティリティ

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferredPrompt: BeforeInstallPromptEvent | null = null;

// Service Workerの登録
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) {
    console.log('Service Worker is not supported');
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register('/sw.js', {
      scope: '/',
    });

    console.log('Service Worker registered:', registration.scope);

    // 更新チェック
    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      if (newWorker) {
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // 新しいバージョンが利用可能
            dispatchEvent(new CustomEvent('sw-update-available'));
          }
        });
      }
    });

    return registration;
  } catch (error) {
    console.error('Service Worker registration failed:', error);
    return null;
  }
}

// インストールプロンプトの保存
export function setupInstallPrompt(): void {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e as BeforeInstallPromptEvent;
    dispatchEvent(new CustomEvent('pwa-installable'));
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    console.log('PWA installed');
  });
}

// インストール可能かどうか
export function isInstallable(): boolean {
  return deferredPrompt !== null;
}

// インストールプロンプトを表示
export async function showInstallPrompt(): Promise<boolean> {
  if (!deferredPrompt) return false;

  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;

  return outcome === 'accepted';
}

// PWAとしてインストール済みかどうか
export function isInstalledPWA(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (window.navigator as any).standalone === true
  );
}

// オンライン状態の監視
export function setupOnlineListener(
  onOnline: () => void,
  onOffline: () => void
): () => void {
  const handleOnline = () => onOnline();
  const handleOffline = () => onOffline();

  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);

  return () => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
  };
}

// プッシュ通知の許可
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    console.log('Notifications are not supported');
    return 'denied';
  }

  return Notification.requestPermission();
}

// プッシュ通知の購読
export async function subscribeToPush(
  registration: ServiceWorkerRegistration,
  vapidPublicKey: string
): Promise<PushSubscription | null> {
  try {
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    });

    console.log('Push subscription:', subscription);
    return subscription;
  } catch (error) {
    console.error('Failed to subscribe to push:', error);
    return null;
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// バックグラウンド同期のリクエスト
export async function requestBackgroundSync(tag: string): Promise<boolean> {
  if (!('serviceWorker' in navigator) || !('SyncManager' in window)) {
    return false;
  }

  try {
    const registration = await navigator.serviceWorker.ready;
    await (registration as any).sync.register(tag);
    return true;
  } catch (error) {
    console.error('Background sync registration failed:', error);
    return false;
  }
}

// IndexedDBへのオフラインデータ保存
export class OfflineStorage {
  private dbName = 'voicescribe-db';
  private dbVersion = 1;

  async open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        if (!db.objectStoreNames.contains('pending-uploads')) {
          db.createObjectStore('pending-uploads', { keyPath: 'id', autoIncrement: true });
        }
        if (!db.objectStoreNames.contains('offline-transcriptions')) {
          const store = db.createObjectStore('offline-transcriptions', { keyPath: 'id' });
          store.createIndex('updatedAt', 'updatedAt');
        }
        if (!db.objectStoreNames.contains('cache-metadata')) {
          db.createObjectStore('cache-metadata', { keyPath: 'key' });
        }
      };
    });
  }

  async savePendingUpload(file: File, metadata: Record<string, any>): Promise<number> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('pending-uploads', 'readwrite');
      const store = tx.objectStore('pending-uploads');

      const request = store.add({
        file,
        metadata,
        createdAt: new Date().toISOString(),
      });

      request.onsuccess = () => resolve(request.result as number);
      request.onerror = () => reject(request.error);
    });
  }

  async getPendingUploads(): Promise<any[]> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('pending-uploads', 'readonly');
      const store = tx.objectStore('pending-uploads');
      const request = store.getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async deletePendingUpload(id: number): Promise<void> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('pending-uploads', 'readwrite');
      const store = tx.objectStore('pending-uploads');
      const request = store.delete(id);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async saveTranscription(transcription: any): Promise<void> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('offline-transcriptions', 'readwrite');
      const store = tx.objectStore('offline-transcriptions');

      const request = store.put({
        ...transcription,
        updatedAt: new Date().toISOString(),
      });

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getTranscription(id: string): Promise<any | null> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('offline-transcriptions', 'readonly');
      const store = tx.objectStore('offline-transcriptions');
      const request = store.get(id);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async getAllTranscriptions(): Promise<any[]> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('offline-transcriptions', 'readonly');
      const store = tx.objectStore('offline-transcriptions');
      const index = store.index('updatedAt');
      const request = index.getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

export const offlineStorage = new OfflineStorage();
