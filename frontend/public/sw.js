const CACHE_NAME = 'voicescribe-v1';
const STATIC_CACHE = 'voicescribe-static-v1';
const DYNAMIC_CACHE = 'voicescribe-dynamic-v1';

// キャッシュするリソース
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/offline.html',
];

// キャッシュしないパス
const EXCLUDE_PATHS = [
  '/api/',
  '/ws/',
  'chrome-extension',
];

// インストール
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('[SW] Caching static assets');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// アクティベート
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== STATIC_CACHE && name !== DYNAMIC_CACHE)
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    })
  );
  self.clients.claim();
});

// フェッチ
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 除外パスのチェック
  if (EXCLUDE_PATHS.some((path) => url.pathname.includes(path) || url.href.includes(path))) {
    return;
  }

  // ナビゲーションリクエスト（HTML）
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // 成功したらキャッシュに保存
          const clone = response.clone();
          caches.open(DYNAMIC_CACHE).then((cache) => {
            cache.put(request, clone);
          });
          return response;
        })
        .catch(() => {
          // オフライン時はキャッシュから返す
          return caches.match(request).then((cached) => {
            if (cached) return cached;
            return caches.match('/offline.html');
          });
        })
    );
    return;
  }

  // その他のリクエスト（CSS, JS, 画像など）
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        // バックグラウンドで更新
        fetch(request).then((response) => {
          if (response.ok) {
            caches.open(DYNAMIC_CACHE).then((cache) => {
              cache.put(request, response);
            });
          }
        });
        return cached;
      }

      return fetch(request).then((response) => {
        if (!response.ok) return response;

        const clone = response.clone();
        caches.open(DYNAMIC_CACHE).then((cache) => {
          cache.put(request, clone);
        });
        return response;
      });
    })
  );
});

// プッシュ通知
self.addEventListener('push', (event) => {
  console.log('[SW] Push received');

  let data = { title: 'VoiceScribe', body: '新しい通知があります' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/icons/icon-192x192.png',
    badge: '/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/',
      dateOfArrival: Date.now(),
    },
    actions: data.actions || [
      { action: 'open', title: '開く' },
      { action: 'close', title: '閉じる' },
    ],
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

// 通知クリック
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked');
  event.notification.close();

  if (event.action === 'close') return;

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // 既存のウィンドウがあればフォーカス
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) {
          return client.focus();
        }
      }
      // なければ新しいウィンドウを開く
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

// バックグラウンド同期
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'sync-transcriptions') {
    event.waitUntil(syncTranscriptions());
  }
});

async function syncTranscriptions() {
  try {
    // IndexedDBから未同期のデータを取得して送信
    const db = await openDB();
    const tx = db.transaction('pending-uploads', 'readonly');
    const store = tx.objectStore('pending-uploads');
    const pendingUploads = await store.getAll();

    for (const upload of pendingUploads) {
      try {
        await fetch('/api/v1/upload', {
          method: 'POST',
          body: upload.formData,
        });
        // 成功したら削除
        const deleteTx = db.transaction('pending-uploads', 'readwrite');
        await deleteTx.objectStore('pending-uploads').delete(upload.id);
      } catch (e) {
        console.error('[SW] Failed to sync upload:', e);
      }
    }
  } catch (e) {
    console.error('[SW] Sync error:', e);
  }
}

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('voicescribe-db', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('pending-uploads')) {
        db.createObjectStore('pending-uploads', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('offline-transcriptions')) {
        db.createObjectStore('offline-transcriptions', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('sync_queue')) {
        const store = db.createObjectStore('sync_queue', { keyPath: 'id' });
        store.createIndex('status', 'status', { unique: false });
      }
    };
  });
}

// 定期的なバックグラウンド同期（Periodic Background Sync API）
self.addEventListener('periodicsync', (event) => {
  console.log('[SW] Periodic sync:', event.tag);

  if (event.tag === 'update-transcriptions') {
    event.waitUntil(updateTranscriptionsCache());
  }

  if (event.tag === 'check-notifications') {
    event.waitUntil(checkForNotifications());
  }
});

async function updateTranscriptionsCache() {
  try {
    const response = await fetch('/api/v1/transcriptions/recent?limit=20');
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      await cache.put('/api/v1/transcriptions/recent', response.clone());
      console.log('[SW] Transcriptions cache updated');
    }
  } catch (e) {
    console.error('[SW] Failed to update transcriptions cache:', e);
  }
}

async function checkForNotifications() {
  try {
    const response = await fetch('/api/v1/notifications/unread');
    if (response.ok) {
      const data = await response.json();
      if (data.count > 0) {
        await self.registration.showNotification('VoiceScribe', {
          body: `${data.count}件の未読通知があります`,
          icon: '/icons/icon-192x192.png',
          badge: '/icons/badge-72x72.png',
          tag: 'unread-notifications',
        });
      }
    }
  } catch (e) {
    console.error('[SW] Failed to check notifications:', e);
  }
}

// メッセージハンドリング
self.addEventListener('message', (event) => {
  console.log('[SW] Message received:', event.data);

  switch (event.data.type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;

    case 'CACHE_URLS':
      const urls = event.data.urls || [];
      caches.open(DYNAMIC_CACHE).then((cache) => {
        cache.addAll(urls).then(() => {
          event.ports[0]?.postMessage({ success: true });
        });
      });
      break;

    case 'CLEAR_CACHE':
      caches.keys().then((keys) => {
        Promise.all(keys.map((key) => caches.delete(key))).then(() => {
          event.ports[0]?.postMessage({ success: true });
        });
      });
      break;

    case 'GET_CACHE_SIZE':
      getCacheSize().then((size) => {
        event.ports[0]?.postMessage({ size });
      });
      break;

    case 'PRECACHE_TRANSCRIPTION':
      precacheTranscription(event.data.id).then(() => {
        event.ports[0]?.postMessage({ success: true });
      });
      break;
  }
});

async function getCacheSize() {
  let totalSize = 0;
  const cacheNames = await caches.keys();

  for (const name of cacheNames) {
    const cache = await caches.open(name);
    const keys = await cache.keys();

    for (const request of keys) {
      const response = await cache.match(request);
      if (response) {
        const blob = await response.clone().blob();
        totalSize += blob.size;
      }
    }
  }

  return totalSize;
}

async function precacheTranscription(id) {
  try {
    const response = await fetch(`/api/v1/transcriptions/${id}`);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      await cache.put(`/api/v1/transcriptions/${id}`, response.clone());
    }
  } catch (e) {
    console.error('[SW] Failed to precache transcription:', e);
  }
}

// オフライン時のフォールバック処理強化
async function handleOfflineRequest(request) {
  const url = new URL(request.url);

  // APIリクエストの場合
  if (url.pathname.startsWith('/api/')) {
    // GETリクエストはキャッシュから返す
    if (request.method === 'GET') {
      const cached = await caches.match(request);
      if (cached) return cached;

      // キャッシュがない場合はオフラインレスポンスを返す
      return new Response(
        JSON.stringify({
          error: 'offline',
          message: 'オフラインです。後で再試行してください。',
        }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    // POST/PUT/DELETEリクエストはキューに追加
    return new Response(
      JSON.stringify({
        queued: true,
        message: 'オフラインです。オンラインになったら自動的に同期されます。',
      }),
      {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }

  // HTMLページの場合
  if (request.destination === 'document') {
    const cached = await caches.match(request);
    if (cached) return cached;
    return caches.match('/offline.html');
  }

  // その他のリソース
  const cached = await caches.match(request);
  if (cached) return cached;

  throw new Error('Resource not available offline');
}
