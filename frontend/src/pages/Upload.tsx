import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Settings2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Dropzone } from '../components/upload/Dropzone';
import { uploadApi, transcriptionApi } from '../lib/api';

interface TranscriptionSettings {
  language: string;
  engine: 'reazon' | 'whisper' | 'hybrid';
  enableDiarization: boolean;
  enableLLMCorrection: boolean;
}

export function Upload() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<TranscriptionSettings>({
    language: 'ja',
    engine: 'hybrid',
    enableDiarization: true,
    enableLLMCorrection: true,
  });

  const handleFileSelect = async (file: File) => {
    setIsUploading(true);
    setError(null);
    setUploadProgress(0);

    try {
      // 1. ファイルを直接アップロード
      setUploadProgress(10);
      const { audio_url } = await uploadApi.directUpload(file);
      setUploadProgress(60);

      // 2. 文字起こしジョブを作成
      const job = await transcriptionApi.create({
        audio_url: audio_url,
        title: file.name.replace(/\.[^/.]+$/, ''),
        language: settings.language,
        engine: settings.engine,
        options: {
          enable_diarization: settings.enableDiarization,
          enable_llm_correction: settings.enableLLMCorrection,
          remove_filler_words: true,
          custom_vocabulary: [],
        },
      });
      setUploadProgress(100);

      // 3. 詳細ページへ遷移
      setTimeout(() => {
        navigate(`/transcriptions/${job.id}`);
      }, 500);
    } catch (err: any) {
      console.error('Upload error:', err);
      const message = err.response?.data?.detail || 'アップロードに失敗しました。もう一度お試しください。';
      setError(message);
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center gap-4 mb-8">
        <Link
          to="/"
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">新規文字起こし</h1>
          <p className="text-gray-500 mt-1">
            音声ファイルをアップロードして文字起こしを開始
          </p>
        </div>
      </div>

      {/* アップロードエリア */}
      <Dropzone
        onFileSelect={handleFileSelect}
        isUploading={isUploading}
        uploadProgress={uploadProgress}
        error={error}
      />

      {/* 設定パネル */}
      <div className="mt-8">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
        >
          <Settings2 className="w-5 h-5" />
          <span className="font-medium">詳細設定</span>
          <span className="text-xs text-gray-400">
            {showSettings ? '▲' : '▼'}
          </span>
        </button>

        {showSettings && (
          <div className="mt-4 p-6 bg-white rounded-xl border border-gray-200 space-y-6">
            {/* 言語 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                言語
              </label>
              <select
                value={settings.language}
                onChange={(e) =>
                  setSettings({ ...settings, language: e.target.value })
                }
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="ja">日本語</option>
                <option value="en">英語</option>
                <option value="zh">中国語</option>
                <option value="ko">韓国語</option>
              </select>
            </div>

            {/* エンジン */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                文字起こしエンジン
              </label>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { value: 'reazon', label: 'ReazonSpeech', desc: '日本語に最適化' },
                  { value: 'whisper', label: 'Whisper', desc: '多言語対応' },
                  { value: 'hybrid', label: 'ハイブリッド', desc: '推奨' },
                ].map((engine) => (
                  <button
                    key={engine.value}
                    onClick={() =>
                      setSettings({
                        ...settings,
                        engine: engine.value as 'reazon' | 'whisper' | 'hybrid',
                      })
                    }
                    className={`p-3 border rounded-lg text-left transition-colors ${
                      settings.engine === engine.value
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="font-medium text-sm">{engine.label}</div>
                    <div className="text-xs text-gray-500">{engine.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* オプション */}
            <div className="space-y-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enableDiarization}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      enableDiarization: e.target.checked,
                    })
                  }
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <div>
                  <div className="font-medium text-sm text-gray-700">
                    話者識別を有効にする
                  </div>
                  <div className="text-xs text-gray-500">
                    複数の話者を自動で識別します
                  </div>
                </div>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enableLLMCorrection}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      enableLLMCorrection: e.target.checked,
                    })
                  }
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <div>
                  <div className="font-medium text-sm text-gray-700">
                    AI補正を有効にする
                  </div>
                  <div className="text-xs text-gray-500">
                    句読点の挿入、表記の修正を自動で行います
                  </div>
                </div>
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
