import { useState } from 'react';
import { X, Download, Bell, Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { usePWA } from '../hooks/usePWA';

export function PWAPrompt() {
  const {
    isOnline,
    isInstallable,
    isInstalled,
    isUpdateAvailable,
    notificationPermission,
    pendingUploadsCount,
    install,
    requestNotifications,
    updateApp,
  } = usePWA();

  const [dismissed, setDismissed] = useState(false);

  // オフラインバナー
  if (!isOnline) {
    return (
      <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-yellow-50 border border-yellow-200 rounded-lg p-4 shadow-lg z-50">
        <div className="flex items-start gap-3">
          <WifiOff className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-yellow-800">オフラインモード</p>
            <p className="text-sm text-yellow-700 mt-1">
              インターネットに接続されていません。一部の機能が制限されます。
            </p>
            {pendingUploadsCount > 0 && (
              <p className="text-sm text-yellow-700 mt-1">
                {pendingUploadsCount}件のアップロードが保留中です
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 更新利用可能バナー
  if (isUpdateAvailable) {
    return (
      <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-lg z-50">
        <div className="flex items-start gap-3">
          <RefreshCw className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-blue-800">アップデートがあります</p>
            <p className="text-sm text-blue-700 mt-1">
              新しいバージョンが利用可能です。
            </p>
            <button
              onClick={updateApp}
              className="mt-2 px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
            >
              今すぐ更新
            </button>
          </div>
        </div>
      </div>
    );
  }

  // インストールプロンプト
  if (isInstallable && !isInstalled && !dismissed) {
    return (
      <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-white border border-gray-200 rounded-lg p-4 shadow-lg z-50">
        <button
          onClick={() => setDismissed(true)}
          className="absolute top-2 right-2 p-1 text-gray-400 hover:text-gray-600"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-blue-100 rounded-lg">
            <Download className="h-5 w-5 text-blue-600" />
          </div>
          <div className="flex-1 pr-4">
            <p className="font-medium text-gray-900">アプリをインストール</p>
            <p className="text-sm text-gray-600 mt-1">
              ホーム画面に追加して、より快適にご利用いただけます。
            </p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={install}
                className="px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
              >
                インストール
              </button>
              <button
                onClick={() => setDismissed(true)}
                className="px-3 py-1.5 text-gray-600 text-sm font-medium hover:text-gray-800"
              >
                後で
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

// 通知許可リクエストコンポーネント
export function NotificationPrompt() {
  const { notificationPermission, requestNotifications } = usePWA();
  const [dismissed, setDismissed] = useState(false);

  if (notificationPermission !== 'default' || dismissed) {
    return null;
  }

  return (
    <div className="bg-blue-50 border-b border-blue-100 px-4 py-3">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Bell className="h-5 w-5 text-blue-600" />
          <p className="text-sm text-blue-800">
            文字起こし完了時に通知を受け取りますか？
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={requestNotifications}
            className="px-3 py-1 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
          >
            許可する
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="px-3 py-1 text-blue-600 text-sm font-medium hover:text-blue-800"
          >
            後で
          </button>
        </div>
      </div>
    </div>
  );
}

// オンライン状態インジケーター
export function OnlineStatus() {
  const { isOnline, pendingUploadsCount } = usePWA();

  if (isOnline && pendingUploadsCount === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1 rounded-full text-sm">
      {isOnline ? (
        <>
          <Wifi className="h-4 w-4 text-green-500" />
          <span className="text-gray-600">オンライン</span>
          {pendingUploadsCount > 0 && (
            <span className="bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full text-xs">
              {pendingUploadsCount}件同期待ち
            </span>
          )}
        </>
      ) : (
        <>
          <WifiOff className="h-4 w-4 text-yellow-500" />
          <span className="text-yellow-700">オフライン</span>
        </>
      )}
    </div>
  );
}
