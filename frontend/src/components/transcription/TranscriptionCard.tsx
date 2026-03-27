import { Link } from 'react-router-dom';
import { FileAudio, Clock, MoreVertical, Trash2, Download, Edit } from 'lucide-react';
import { useState } from 'react';
import type { Transcription } from '../../types';
import {
  formatDuration,
  formatRelativeTime,
  getStatusColor,
  getStatusLabel,
} from '../../lib/utils';

interface TranscriptionCardProps {
  transcription: Transcription;
  onDelete?: (id: string) => void;
  onExport?: (id: string) => void;
}

export function TranscriptionCard({
  transcription,
  onDelete,
  onExport,
}: TranscriptionCardProps) {
  const [showMenu, setShowMenu] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
          <FileAudio className="w-6 h-6 text-gray-500" />
        </div>

        <div className="flex-1 min-w-0">
          <Link
            to={`/transcriptions/${transcription.id}`}
            className="font-medium text-gray-900 hover:text-primary-600 truncate block"
          >
            {transcription.title || '無題の文字起こし'}
          </Link>

          <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
            {transcription.audio_duration_sec && (
              <span className="flex items-center gap-1">
                <Clock className="w-4 h-4" />
                {formatDuration(transcription.audio_duration_sec)}
              </span>
            )}
            <span>{formatRelativeTime(transcription.created_at)}</span>
          </div>

          <div className="mt-2">
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
          </div>
        </div>

        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
          >
            <MoreVertical className="w-5 h-5" />
          </button>

          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-20">
                <Link
                  to={`/transcriptions/${transcription.id}`}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  <Edit className="w-4 h-4" />
                  編集
                </Link>
                {transcription.status === 'completed' && onExport && (
                  <button
                    onClick={() => {
                      onExport(transcription.id);
                      setShowMenu(false);
                    }}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 w-full text-left"
                  >
                    <Download className="w-4 h-4" />
                    エクスポート
                  </button>
                )}
                {onDelete && (
                  <button
                    onClick={() => {
                      onDelete(transcription.id);
                      setShowMenu(false);
                    }}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50 w-full text-left"
                  >
                    <Trash2 className="w-4 h-4" />
                    削除
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
