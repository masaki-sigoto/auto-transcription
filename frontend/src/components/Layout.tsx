import { Link, Outlet, useLocation } from 'react-router-dom';
import { FileAudio, Upload, Settings, Menu, X, Mic, Link2, Users, BookOpen, Code } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../lib/utils';
import { OnlineStatus } from './PWAPrompt';

const navigation = [
  { name: 'ダッシュボード', href: '/', icon: FileAudio },
  { name: '新規アップロード', href: '/upload', icon: Upload },
  { name: 'リアルタイム', href: '/realtime', icon: Mic },
  { name: 'チーム', href: '/teams', icon: Users },
  { name: '連携設定', href: '/integrations', icon: Link2 },
  { name: 'カスタム語彙', href: '/vocabulary', icon: BookOpen },
  { name: '開発者', href: '/developer', icon: Code },
  { name: '設定', href: '/settings', icon: Settings },
];

export function Layout() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* モバイルサイドバー背景 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-gray-600/75 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* サイドバー */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 transform transition-transform lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex items-center justify-between h-16 px-6 border-b border-gray-200">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <FileAudio className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold text-gray-900">VoiceScribe</span>
          </Link>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 text-gray-500 hover:text-gray-700"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-100'
                )}
              >
                <item.icon className="w-5 h-5" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* 使用量表示 */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200">
          <div className="text-sm">
            <div className="flex justify-between text-gray-600 mb-1">
              <span>今月の使用量</span>
              <span>30 / 60分</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary-600 h-2 rounded-full"
                style={{ width: '50%' }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Freeプラン - 月60分まで
            </p>
          </div>
        </div>
      </aside>

      {/* メインコンテンツ */}
      <div className="lg:pl-64">
        {/* ヘッダー */}
        <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
          <div className="flex items-center h-16 px-4 gap-4">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 text-gray-500 hover:text-gray-700"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="flex-1" />
            <OnlineStatus />
            {/* ユーザーメニュー（プレースホルダー） */}
            <div className="w-8 h-8 bg-gray-200 rounded-full" />
          </div>
        </header>

        {/* ページコンテンツ */}
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
