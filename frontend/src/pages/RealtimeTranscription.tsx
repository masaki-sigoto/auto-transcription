import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Mic, MicOff, Save, Trash2, Settings2 } from 'lucide-react';
import { useRealtime } from '../hooks/useRealtime';
import { Button } from '../components/ui/Button';
import { transcriptionApi } from '../lib/api';
import { cn } from '../lib/utils';

export function RealtimeTranscription() {
  const navigate = useNavigate();
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState({
    language: 'ja',
    engine: 'reazon' as 'reazon' | 'whisper' | 'hybrid',
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    isRecording,
    isConnected,
    segments,
    startRecording,
    stopRecording,
    getFullText,
  } = useRealtime({
    language: settings.language,
    engine: settings.engine,
    onError: setError,
  });

  const handleSave = async () => {
    if (segments.length === 0) return;

    setIsSaving(true);
    try {
      // TODO: リアルタイム文字起こし結果を保存するAPIを呼び出す
      // 現状は新規作成として保存
      const fullText = getFullText();
      console.log('Saving transcription:', fullText);

      // 仮: ダッシュボードに戻る
      navigate('/');
    } catch (err) {
      setError('保存に失敗しました');
    } finally {
      setIsSaving(false);
    }
  };

  const handleClear = () => {
    if (window.confirm('文字起こし結果をクリアしますか？')) {
      window.location.reload();
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              リアルタイム文字起こし
            </h1>
            <p className="text-gray-500 mt-1">
              マイクから直接文字起こしを行います
            </p>
          </div>
        </div>

        <button
          onClick={() => setShowSettings(!showSettings)}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <Settings2 className="w-5 h-5" />
        </button>
      </div>

      {/* 設定パネル */}
      {showSettings && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-gray-200">
          <h3 className="font-medium text-gray-900 mb-4">設定</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                言語
              </label>
              <select
                value={settings.language}
                onChange={(e) =>
                  setSettings({ ...settings, language: e.target.value })
                }
                disabled={isRecording}
                className="w-full p-2 border border-gray-300 rounded-lg disabled:opacity-50"
              >
                <option value="ja">日本語</option>
                <option value="en">英語</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                エンジン
              </label>
              <select
                value={settings.engine}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    engine: e.target.value as 'reazon' | 'whisper' | 'hybrid',
                  })
                }
                disabled={isRecording}
                className="w-full p-2 border border-gray-300 rounded-lg disabled:opacity-50"
              >
                <option value="reazon">ReazonSpeech</option>
                <option value="whisper">Whisper</option>
                <option value="hybrid">ハイブリッド</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* エラー表示 */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-600">
          {error}
        </div>
      )}

      {/* 録音コントロール */}
      <div className="flex justify-center mb-8">
        <button
          onClick={isRecording ? stopRecording : startRecording}
          className={cn(
            'w-24 h-24 rounded-full flex items-center justify-center transition-all',
            isRecording
              ? 'bg-red-500 hover:bg-red-600 animate-pulse'
              : 'bg-primary-600 hover:bg-primary-700'
          )}
        >
          {isRecording ? (
            <MicOff className="w-10 h-10 text-white" />
          ) : (
            <Mic className="w-10 h-10 text-white" />
          )}
        </button>
      </div>

      {/* 接続状態 */}
      <div className="flex justify-center mb-6">
        <div className="flex items-center gap-2 text-sm">
          <div
            className={cn(
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-green-500' : 'bg-gray-300'
            )}
          />
          <span className="text-gray-500">
            {isRecording
              ? isConnected
                ? '録音中...'
                : '接続中...'
              : 'クリックして録音開始'}
          </span>
        </div>
      </div>

      {/* 文字起こし結果 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 min-h-[300px]">
        {segments.length === 0 ? (
          <div className="text-center text-gray-400 py-12">
            録音を開始すると、ここに文字起こし結果が表示されます
          </div>
        ) : (
          <div className="space-y-2">
            {segments.map((segment, index) => (
              <span
                key={index}
                className={cn(
                  'inline',
                  segment.is_final ? 'text-gray-900' : 'text-gray-400'
                )}
              >
                {segment.text}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* アクションボタン */}
      {segments.length > 0 && !isRecording && (
        <div className="flex justify-center gap-4 mt-6">
          <Button onClick={handleSave} isLoading={isSaving}>
            <Save className="w-4 h-4 mr-2" />
            保存
          </Button>
          <Button variant="secondary" onClick={handleClear}>
            <Trash2 className="w-4 h-4 mr-2" />
            クリア
          </Button>
        </div>
      )}

      {/* 使い方ヒント */}
      <div className="mt-8 p-4 bg-gray-50 rounded-lg">
        <h3 className="font-medium text-gray-900 mb-2">使い方</h3>
        <ul className="text-sm text-gray-600 space-y-1">
          <li>1. マイクボタンをクリックして録音を開始</li>
          <li>2. 話し始めると自動的に文字起こしされます</li>
          <li>3. 再度ボタンをクリックして録音を停止</li>
          <li>4. 結果を確認して保存</li>
        </ul>
      </div>
    </div>
  );
}
