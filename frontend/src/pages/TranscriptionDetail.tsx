import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Download, Sparkles, Share2, MoreVertical } from 'lucide-react';
import { useState } from 'react';
import {
  useTranscription,
  useUpdateSegment,
  useExportTranscription,
  useSummarizeTranscription,
} from '../hooks/useTranscription';
import { useAudioPlayer } from '../hooks/useAudioPlayer';
import { Editor } from '../components/transcription/Editor';
import { AudioPlayer } from '../components/transcription/AudioPlayer';
import { Button } from '../components/ui/Button';
import { getStatusColor, getStatusLabel } from '../lib/utils';
import type { Summary } from '../types';

export function TranscriptionDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: transcription, isLoading, error } = useTranscription(id || '');
  const updateSegment = useUpdateSegment();
  const exportTranscription = useExportTranscription();
  const summarize = useSummarizeTranscription();

  const [showExportMenu, setShowExportMenu] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [showSummary, setShowSummary] = useState(false);

  const {
    duration,
    currentTime,
    isPlaying,
    isReady,
    togglePlay,
    seek,
    seekToSegment,
    skip,
  } = useAudioPlayer(transcription?.audio_url || null);

  const handleSegmentUpdate = async (segmentId: string, text: string) => {
    await updateSegment.mutateAsync({ segmentId, updates: { text } });
  };

  const handleExport = async (format: 'txt' | 'srt' | 'vtt' | 'docx' | 'json') => {
    if (!id) return;
    const result = await exportTranscription.mutateAsync({
      id,
      request: { format },
    });
    window.open(result.download_url, '_blank');
    setShowExportMenu(false);
  };

  const handleSummarize = async () => {
    if (!id) return;
    const result = await summarize.mutateAsync(id);
    setSummary(result);
    setShowSummary(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full mx-auto" />
          <p className="mt-4 text-gray-500">読み込み中...</p>
        </div>
      </div>
    );
  }

  if (error || !transcription) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-600">
          文字起こしデータの取得に失敗しました。
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {transcription.title || '無題の文字起こし'}
            </h1>
            <div className="flex items-center gap-3 mt-1">
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                  transcription.status
                )}`}
              >
                {transcription.status === 'processing' && (
                  <svg className="animate-spin -ml-0.5 mr-1 h-3 w-3" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                )}
                {getStatusLabel(transcription.status)}
              </span>
              <span className="text-sm text-gray-500">
                {transcription.language.toUpperCase()} / {transcription.engine}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* AI要約ボタン */}
          {transcription.status === 'completed' && (
            <Button
              variant="secondary"
              onClick={handleSummarize}
              isLoading={summarize.isPending}
            >
              <Sparkles className="w-4 h-4 mr-2" />
              AI要約
            </Button>
          )}

          {/* エクスポートメニュー */}
          {transcription.status === 'completed' && (
            <div className="relative">
              <Button variant="secondary" onClick={() => setShowExportMenu(!showExportMenu)}>
                <Download className="w-4 h-4 mr-2" />
                エクスポート
              </Button>
              {showExportMenu && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowExportMenu(false)}
                  />
                  <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-20">
                    {[
                      { format: 'txt', label: 'テキスト (.txt)' },
                      { format: 'srt', label: '字幕 (.srt)' },
                      { format: 'vtt', label: 'WebVTT (.vtt)' },
                      { format: 'docx', label: 'Word (.docx)' },
                      { format: 'json', label: 'JSON (.json)' },
                    ].map((item) => (
                      <button
                        key={item.format}
                        onClick={() => handleExport(item.format as any)}
                        className="w-full px-4 py-2 text-sm text-left text-gray-700 hover:bg-gray-100"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          <Button variant="ghost">
            <Share2 className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* 処理中の場合 */}
      {transcription.status === 'processing' && (
        <div className="flex-1 flex items-center justify-center bg-gray-50">
          <div className="text-center">
            <div className="animate-spin w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full mx-auto" />
            <h3 className="text-lg font-medium text-gray-900 mt-6">処理中...</h3>
            <p className="text-gray-500 mt-2">
              文字起こしが完了するまでお待ちください
            </p>
          </div>
        </div>
      )}

      {/* 失敗の場合 */}
      {transcription.status === 'failed' && (
        <div className="flex-1 flex items-center justify-center bg-gray-50">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
              <span className="text-3xl">😞</span>
            </div>
            <h3 className="text-lg font-medium text-gray-900 mt-6">
              処理に失敗しました
            </h3>
            <p className="text-gray-500 mt-2">{transcription.error_message}</p>
            <Button className="mt-6">もう一度試す</Button>
          </div>
        </div>
      )}

      {/* 完了の場合: エディター */}
      {transcription.status === 'completed' && (
        <>
          <Editor
            segments={transcription.segments}
            speakers={transcription.speakers}
            onSegmentUpdate={handleSegmentUpdate}
            onSeekToSegment={seekToSegment}
          />
          <AudioPlayer
            duration={duration}
            currentTime={currentTime}
            isPlaying={isPlaying}
            isReady={isReady}
            onTogglePlay={togglePlay}
            onSeek={seek}
            onSkip={skip}
          />
        </>
      )}

      {/* AI要約モーダル */}
      {showSummary && summary && (
        <>
          <div
            className="fixed inset-0 bg-black/50 z-40"
            onClick={() => setShowSummary(false)}
          />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl bg-white rounded-xl shadow-xl z-50 max-h-[80vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary-600" />
                  AI要約
                </h2>
                <button
                  onClick={() => setShowSummary(false)}
                  className="p-2 text-gray-400 hover:text-gray-600"
                >
                  ×
                </button>
              </div>

              <div className="space-y-6">
                {/* 要約 */}
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">概要</h3>
                  <p className="text-gray-600">{summary.summary}</p>
                </div>

                {/* トピック */}
                {summary.topics.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">主なトピック</h3>
                    <ul className="list-disc list-inside space-y-1 text-gray-600">
                      {summary.topics.map((topic, i) => (
                        <li key={i}>{topic}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 決定事項 */}
                {summary.decisions.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">決定事項</h3>
                    <ul className="list-disc list-inside space-y-1 text-gray-600">
                      {summary.decisions.map((decision, i) => (
                        <li key={i}>{decision}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* アクションアイテム */}
                {summary.action_items.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">
                      アクションアイテム
                    </h3>
                    <ul className="list-disc list-inside space-y-1 text-gray-600">
                      {summary.action_items.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
