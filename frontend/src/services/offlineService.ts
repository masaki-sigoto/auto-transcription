/**
 * 高度なオフライン対応・PWAサービス
 */

// IndexedDB データベース名とバージョン
const DB_NAME = 'transcription-offline-db';
const DB_VERSION = 1;

// ストア名
const STORES = {
  TRANSCRIPTIONS: 'transcriptions',
  AUDIO_FILES: 'audio_files',
  SYNC_QUEUE: 'sync_queue',
  SETTINGS: 'settings',
  CACHE_METADATA: 'cache_metadata',
};

// 同期状態
type SyncStatus = 'pending' | 'syncing' | 'synced' | 'error';

interface SyncQueueItem {
  id: string;
  action: 'create' | 'update' | 'delete';
  entity: string;
  data: any;
  timestamp: number;
  retryCount: number;
  status: SyncStatus;
  errorMessage?: string;
}

interface OfflineTranscription {
  id: string;
  title: string;
  content: string;
  audioFileId?: string;
  createdAt: number;
  updatedAt: number;
  syncStatus: SyncStatus;
  localOnly: boolean;
}

interface CachedAudioFile {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
  blob: Blob;
  createdAt: number;
}

class IndexedDBManager {
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // 文字起こしストア
        if (!db.objectStoreNames.contains(STORES.TRANSCRIPTIONS)) {
          const store = db.createObjectStore(STORES.TRANSCRIPTIONS, { keyPath: 'id' });
          store.createIndex('syncStatus', 'syncStatus', { unique: false });
          store.createIndex('updatedAt', 'updatedAt', { unique: false });
        }

        // 音声ファイルストア
        if (!db.objectStoreNames.contains(STORES.AUDIO_FILES)) {
          const store = db.createObjectStore(STORES.AUDIO_FILES, { keyPath: 'id' });
          store.createIndex('createdAt', 'createdAt', { unique: false });
        }

        // 同期キューストア
        if (!db.objectStoreNames.contains(STORES.SYNC_QUEUE)) {
          const store = db.createObjectStore(STORES.SYNC_QUEUE, { keyPath: 'id' });
          store.createIndex('status', 'status', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }

        // 設定ストア
        if (!db.objectStoreNames.contains(STORES.SETTINGS)) {
          db.createObjectStore(STORES.SETTINGS, { keyPath: 'key' });
        }

        // キャッシュメタデータストア
        if (!db.objectStoreNames.contains(STORES.CACHE_METADATA)) {
          db.createObjectStore(STORES.CACHE_METADATA, { keyPath: 'key' });
        }
      };
    });
  }

  private getStore(storeName: string, mode: IDBTransactionMode = 'readonly'): IDBObjectStore {
    if (!this.db) throw new Error('Database not initialized');
    const transaction = this.db.transaction(storeName, mode);
    return transaction.objectStore(storeName);
  }

  async get<T>(storeName: string, key: string): Promise<T | undefined> {
    return new Promise((resolve, reject) => {
      const store = this.getStore(storeName);
      const request = store.get(key);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async getAll<T>(storeName: string): Promise<T[]> {
    return new Promise((resolve, reject) => {
      const store = this.getStore(storeName);
      const request = store.getAll();
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async put<T>(storeName: string, data: T): Promise<void> {
    return new Promise((resolve, reject) => {
      const store = this.getStore(storeName, 'readwrite');
      const request = store.put(data);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve();
    });
  }

  async delete(storeName: string, key: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const store = this.getStore(storeName, 'readwrite');
      const request = store.delete(key);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve();
    });
  }

  async getByIndex<T>(storeName: string, indexName: string, value: any): Promise<T[]> {
    return new Promise((resolve, reject) => {
      const store = this.getStore(storeName);
      const index = store.index(indexName);
      const request = index.getAll(value);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }
}

class OfflineTranscriptionService {
  private db: IndexedDBManager;

  constructor(db: IndexedDBManager) {
    this.db = db;
  }

  async saveTranscription(transcription: Partial<OfflineTranscription>): Promise<OfflineTranscription> {
    const now = Date.now();
    const data: OfflineTranscription = {
      id: transcription.id || crypto.randomUUID(),
      title: transcription.title || '無題の文字起こし',
      content: transcription.content || '',
      audioFileId: transcription.audioFileId,
      createdAt: transcription.createdAt || now,
      updatedAt: now,
      syncStatus: 'pending',
      localOnly: true,
    };

    await this.db.put(STORES.TRANSCRIPTIONS, data);
    return data;
  }

  async getTranscription(id: string): Promise<OfflineTranscription | undefined> {
    return this.db.get(STORES.TRANSCRIPTIONS, id);
  }

  async getAllTranscriptions(): Promise<OfflineTranscription[]> {
    return this.db.getAll(STORES.TRANSCRIPTIONS);
  }

  async getPendingTranscriptions(): Promise<OfflineTranscription[]> {
    return this.db.getByIndex(STORES.TRANSCRIPTIONS, 'syncStatus', 'pending');
  }

  async deleteTranscription(id: string): Promise<void> {
    await this.db.delete(STORES.TRANSCRIPTIONS, id);
  }

  async updateSyncStatus(id: string, status: SyncStatus): Promise<void> {
    const transcription = await this.getTranscription(id);
    if (transcription) {
      transcription.syncStatus = status;
      transcription.localOnly = status !== 'synced';
      await this.db.put(STORES.TRANSCRIPTIONS, transcription);
    }
  }
}

class AudioCacheService {
  private db: IndexedDBManager;
  private maxCacheSize: number = 500 * 1024 * 1024; // 500MB

  constructor(db: IndexedDBManager) {
    this.db = db;
  }

  async cacheAudioFile(file: File): Promise<CachedAudioFile> {
    // キャッシュサイズをチェック
    await this.ensureCacheSpace(file.size);

    const cached: CachedAudioFile = {
      id: crypto.randomUUID(),
      filename: file.name,
      mimeType: file.type,
      size: file.size,
      blob: file,
      createdAt: Date.now(),
    };

    await this.db.put(STORES.AUDIO_FILES, cached);
    return cached;
  }

  async getAudioFile(id: string): Promise<CachedAudioFile | undefined> {
    return this.db.get(STORES.AUDIO_FILES, id);
  }

  async getAllCachedFiles(): Promise<CachedAudioFile[]> {
    return this.db.getAll(STORES.AUDIO_FILES);
  }

  async deleteAudioFile(id: string): Promise<void> {
    await this.db.delete(STORES.AUDIO_FILES, id);
  }

  async getCacheSize(): Promise<number> {
    const files = await this.getAllCachedFiles();
    return files.reduce((total, file) => total + file.size, 0);
  }

  private async ensureCacheSpace(requiredSize: number): Promise<void> {
    const currentSize = await this.getCacheSize();
    if (currentSize + requiredSize <= this.maxCacheSize) return;

    // 古いファイルから削除
    const files = await this.getAllCachedFiles();
    files.sort((a, b) => a.createdAt - b.createdAt);

    let freedSize = 0;
    for (const file of files) {
      if (currentSize - freedSize + requiredSize <= this.maxCacheSize) break;
      await this.deleteAudioFile(file.id);
      freedSize += file.size;
    }
  }

  async clearCache(): Promise<void> {
    const files = await this.getAllCachedFiles();
    for (const file of files) {
      await this.deleteAudioFile(file.id);
    }
  }
}

class SyncQueueService {
  private db: IndexedDBManager;
  private maxRetries: number = 3;
  private isSyncing: boolean = false;

  constructor(db: IndexedDBManager) {
    this.db = db;
  }

  async addToQueue(action: SyncQueueItem['action'], entity: string, data: any): Promise<void> {
    const item: SyncQueueItem = {
      id: crypto.randomUUID(),
      action,
      entity,
      data,
      timestamp: Date.now(),
      retryCount: 0,
      status: 'pending',
    };

    await this.db.put(STORES.SYNC_QUEUE, item);
  }

  async getPendingItems(): Promise<SyncQueueItem[]> {
    return this.db.getByIndex(STORES.SYNC_QUEUE, 'status', 'pending');
  }

  async processQueue(): Promise<void> {
    if (this.isSyncing || !navigator.onLine) return;

    this.isSyncing = true;
    try {
      const pendingItems = await this.getPendingItems();

      for (const item of pendingItems) {
        try {
          await this.syncItem(item);
          item.status = 'synced';
          await this.db.put(STORES.SYNC_QUEUE, item);
        } catch (error) {
          item.retryCount++;
          item.errorMessage = error instanceof Error ? error.message : 'Unknown error';

          if (item.retryCount >= this.maxRetries) {
            item.status = 'error';
          }

          await this.db.put(STORES.SYNC_QUEUE, item);
        }
      }
    } finally {
      this.isSyncing = false;
    }
  }

  private async syncItem(item: SyncQueueItem): Promise<void> {
    const endpoint = `/api/v1/${item.entity}`;

    let method: string;
    let url: string;

    switch (item.action) {
      case 'create':
        method = 'POST';
        url = endpoint;
        break;
      case 'update':
        method = 'PUT';
        url = `${endpoint}/${item.data.id}`;
        break;
      case 'delete':
        method = 'DELETE';
        url = `${endpoint}/${item.data.id}`;
        break;
    }

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: item.action !== 'delete' ? JSON.stringify(item.data) : undefined,
    });

    if (!response.ok) {
      throw new Error(`Sync failed: ${response.status}`);
    }
  }

  async clearSyncedItems(): Promise<void> {
    const items = await this.db.getByIndex<SyncQueueItem>(STORES.SYNC_QUEUE, 'status', 'synced');
    for (const item of items) {
      await this.db.delete(STORES.SYNC_QUEUE, item.id);
    }
  }
}

class BackgroundSyncManager {
  private registration: ServiceWorkerRegistration | null = null;

  async init(): Promise<void> {
    if ('serviceWorker' in navigator && 'sync' in window) {
      this.registration = await navigator.serviceWorker.ready;
    }
  }

  async requestSync(tag: string = 'transcription-sync'): Promise<void> {
    if (this.registration && 'sync' in this.registration) {
      try {
        await (this.registration as any).sync.register(tag);
      } catch (error) {
        console.warn('Background sync not supported:', error);
      }
    }
  }
}

class NetworkStatusManager {
  private listeners: Set<(online: boolean) => void> = new Set();
  private _isOnline: boolean = navigator.onLine;

  constructor() {
    window.addEventListener('online', () => this.handleStatusChange(true));
    window.addEventListener('offline', () => this.handleStatusChange(false));
  }

  get isOnline(): boolean {
    return this._isOnline;
  }

  private handleStatusChange(online: boolean): void {
    this._isOnline = online;
    this.listeners.forEach(listener => listener(online));
  }

  subscribe(listener: (online: boolean) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async checkConnectivity(): Promise<boolean> {
    try {
      const response = await fetch('/api/v1/health', { method: 'HEAD' });
      return response.ok;
    } catch {
      return false;
    }
  }
}

// PWAインストール管理
class PWAInstallManager {
  private deferredPrompt: any = null;
  private listeners: Set<(canInstall: boolean) => void> = new Set();

  constructor() {
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      this.deferredPrompt = e;
      this.notifyListeners(true);
    });

    window.addEventListener('appinstalled', () => {
      this.deferredPrompt = null;
      this.notifyListeners(false);
    });
  }

  get canInstall(): boolean {
    return this.deferredPrompt !== null;
  }

  async promptInstall(): Promise<boolean> {
    if (!this.deferredPrompt) return false;

    this.deferredPrompt.prompt();
    const { outcome } = await this.deferredPrompt.userChoice;
    this.deferredPrompt = null;

    return outcome === 'accepted';
  }

  subscribe(listener: (canInstall: boolean) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(canInstall: boolean): void {
    this.listeners.forEach(listener => listener(canInstall));
  }

  isStandalone(): boolean {
    return window.matchMedia('(display-mode: standalone)').matches ||
           (window.navigator as any).standalone === true;
  }
}

// プッシュ通知管理
class PushNotificationManager {
  private registration: ServiceWorkerRegistration | null = null;

  async init(): Promise<void> {
    if ('serviceWorker' in navigator && 'PushManager' in window) {
      this.registration = await navigator.serviceWorker.ready;
    }
  }

  async requestPermission(): Promise<NotificationPermission> {
    return Notification.requestPermission();
  }

  async subscribe(serverKey: string): Promise<PushSubscription | null> {
    if (!this.registration) return null;

    try {
      const subscription = await this.registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(serverKey),
      });

      // サーバーに購読情報を送信
      await fetch('/api/v1/notifications/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription),
      });

      return subscription;
    } catch (error) {
      console.error('Push subscription failed:', error);
      return null;
    }
  }

  async unsubscribe(): Promise<boolean> {
    if (!this.registration) return false;

    try {
      const subscription = await this.registration.pushManager.getSubscription();
      if (subscription) {
        await subscription.unsubscribe();
        return true;
      }
    } catch (error) {
      console.error('Push unsubscription failed:', error);
    }
    return false;
  }

  private urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }
}

// メインのオフラインサービス
export class OfflineService {
  private db: IndexedDBManager;
  public transcriptions: OfflineTranscriptionService;
  public audioCache: AudioCacheService;
  public syncQueue: SyncQueueService;
  public backgroundSync: BackgroundSyncManager;
  public networkStatus: NetworkStatusManager;
  public pwaInstall: PWAInstallManager;
  public pushNotifications: PushNotificationManager;

  private initialized: boolean = false;

  constructor() {
    this.db = new IndexedDBManager();
    this.transcriptions = new OfflineTranscriptionService(this.db);
    this.audioCache = new AudioCacheService(this.db);
    this.syncQueue = new SyncQueueService(this.db);
    this.backgroundSync = new BackgroundSyncManager();
    this.networkStatus = new NetworkStatusManager();
    this.pwaInstall = new PWAInstallManager();
    this.pushNotifications = new PushNotificationManager();
  }

  async init(): Promise<void> {
    if (this.initialized) return;

    await this.db.init();
    await this.backgroundSync.init();
    await this.pushNotifications.init();

    // オンラインになったら同期を開始
    this.networkStatus.subscribe((online) => {
      if (online) {
        this.syncQueue.processQueue();
        this.backgroundSync.requestSync();
      }
    });

    this.initialized = true;
  }

  async getStorageEstimate(): Promise<{ usage: number; quota: number }> {
    if ('storage' in navigator && 'estimate' in navigator.storage) {
      const estimate = await navigator.storage.estimate();
      return {
        usage: estimate.usage || 0,
        quota: estimate.quota || 0,
      };
    }
    return { usage: 0, quota: 0 };
  }

  async requestPersistentStorage(): Promise<boolean> {
    if ('storage' in navigator && 'persist' in navigator.storage) {
      return navigator.storage.persist();
    }
    return false;
  }
}

// シングルトンインスタンス
export const offlineService = new OfflineService();
