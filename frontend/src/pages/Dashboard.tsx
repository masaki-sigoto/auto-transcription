import { Link } from 'react-router-dom';
import { Plus, Search, Filter, FileAudio } from 'lucide-react';
import { useState } from 'react';
import { useTranscriptions, useDeleteTranscription } from '../hooks/useTranscription';
import { TranscriptionCard } from '../components/transcription/TranscriptionCard';
import { Button } from '../components/ui/Button';

export function Dashboard() {
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const { data, isLoading, error } = useTranscriptions(page, 20);
  const deleteTranscription = useDeleteTranscription();

  const handleDelete = async (id: string) => {
    if (window.confirm('この文字起こしを削除しますか？')) {
      await deleteTranscription.mutateAsync(id);
    }
  };

  const handleExport = (id: string) => {
    // TODO: エクスポートモーダルを開く
    console.log('Export:', id);
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">文字起こし一覧</h1>
          <p className="text-gray-500 mt-1">
            {data?.total || 0} 件の文字起こし
          </p>
        </div>
        <Link to="/upload">
          <Button>
            <Plus className="w-4 h-4 mr-2" />
            新規作成
          </Button>
        </Link>
      </div>

      {/* 検索・フィルター */}
      <div className="flex gap-4 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="検索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <Button variant="secondary">
          <Filter className="w-4 h-4 mr-2" />
          フィルター
        </Button>
      </div>

      {/* ローディング */}
      {isLoading && (
        <div className="text-center py-12">
          <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full mx-auto" />
          <p className="mt-4 text-gray-500">読み込み中...</p>
        </div>
      )}

      {/* エラー */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-600">
          データの取得に失敗しました。
        </div>
      )}

      {/* 文字起こし一覧 */}
      {data && data.items.length > 0 ? (
        <div className="space-y-4">
          {data.items.map((transcription) => (
            <TranscriptionCard
              key={transcription.id}
              transcription={transcription}
              onDelete={handleDelete}
              onExport={handleExport}
            />
          ))}
        </div>
      ) : (
        !isLoading && (
          <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
            <FileAudio className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              文字起こしがありません
            </h3>
            <p className="text-gray-500 mb-6">
              音声ファイルをアップロードして、文字起こしを開始しましょう
            </p>
            <Link to="/upload">
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                最初の文字起こしを作成
              </Button>
            </Link>
          </div>
        )
      )}

      {/* ページネーション */}
      {data && data.total > 20 && (
        <div className="flex justify-center gap-2 mt-8">
          <Button
            variant="secondary"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            前へ
          </Button>
          <span className="px-4 py-2 text-gray-600">
            {page} / {Math.ceil(data.total / 20)}
          </span>
          <Button
            variant="secondary"
            disabled={page >= Math.ceil(data.total / 20)}
            onClick={() => setPage((p) => p + 1)}
          >
            次へ
          </Button>
        </div>
      )}
    </div>
  );
}
