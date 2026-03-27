import { useState } from 'react';
import { Button } from '../components/ui/Button';

export function Settings() {
  const [settings, setSettings] = useState({
    defaultLanguage: 'ja',
    defaultEngine: 'hybrid',
    autoDeleteDays: 30,
    emailNotifications: true,
  });

  const handleSave = () => {
    // TODO: 設定を保存
    console.log('Settings saved:', settings);
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-8">設定</h1>

      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-200">
        {/* デフォルト言語 */}
        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">デフォルト言語</h3>
          <p className="text-sm text-gray-500 mb-4">
            新規文字起こしのデフォルト言語を設定します
          </p>
          <select
            value={settings.defaultLanguage}
            onChange={(e) =>
              setSettings({ ...settings, defaultLanguage: e.target.value })
            }
            className="w-full max-w-xs p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="ja">日本語</option>
            <option value="en">英語</option>
            <option value="zh">中国語</option>
            <option value="ko">韓国語</option>
          </select>
        </div>

        {/* デフォルトエンジン */}
        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">
            デフォルト文字起こしエンジン
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            新規文字起こしで使用するエンジンを設定します
          </p>
          <select
            value={settings.defaultEngine}
            onChange={(e) =>
              setSettings({ ...settings, defaultEngine: e.target.value })
            }
            className="w-full max-w-xs p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="reazon">ReazonSpeech（日本語最適化）</option>
            <option value="whisper">Whisper（多言語対応）</option>
            <option value="hybrid">ハイブリッド（推奨）</option>
          </select>
        </div>

        {/* 自動削除 */}
        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">音声ファイルの自動削除</h3>
          <p className="text-sm text-gray-500 mb-4">
            処理完了後に音声ファイルを自動削除するまでの日数
          </p>
          <select
            value={settings.autoDeleteDays}
            onChange={(e) =>
              setSettings({ ...settings, autoDeleteDays: parseInt(e.target.value) })
            }
            className="w-full max-w-xs p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="1">1日</option>
            <option value="7">7日</option>
            <option value="30">30日</option>
            <option value="90">90日</option>
            <option value="0">削除しない</option>
          </select>
        </div>

        {/* メール通知 */}
        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">メール通知</h3>
          <p className="text-sm text-gray-500 mb-4">
            文字起こし完了時にメールで通知を受け取ります
          </p>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.emailNotifications}
              onChange={(e) =>
                setSettings({ ...settings, emailNotifications: e.target.checked })
              }
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <span className="text-gray-700">通知を受け取る</span>
          </label>
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <Button onClick={handleSave}>設定を保存</Button>
      </div>

      {/* アカウント */}
      <h2 className="text-xl font-bold text-gray-900 mt-12 mb-6">アカウント</h2>
      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-200">
        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">プラン</h3>
          <p className="text-sm text-gray-500 mb-4">現在のプラン: Free</p>
          <Button variant="secondary">プランをアップグレード</Button>
        </div>

        <div className="p-6">
          <h3 className="font-medium text-gray-900 mb-1">データのエクスポート</h3>
          <p className="text-sm text-gray-500 mb-4">
            すべての文字起こしデータをダウンロードします
          </p>
          <Button variant="secondary">データをエクスポート</Button>
        </div>

        <div className="p-6">
          <h3 className="font-medium text-red-600 mb-1">アカウントの削除</h3>
          <p className="text-sm text-gray-500 mb-4">
            アカウントとすべてのデータを完全に削除します。この操作は取り消せません。
          </p>
          <Button variant="danger">アカウントを削除</Button>
        </div>
      </div>
    </div>
  );
}
