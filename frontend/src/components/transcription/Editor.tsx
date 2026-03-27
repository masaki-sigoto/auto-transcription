import { useState, useRef, useEffect } from 'react';
import { Edit2, Check, X } from 'lucide-react';
import type { Segment, Speaker } from '../../types';
import { formatTimestamp, cn } from '../../lib/utils';
import { useTranscriptionStore } from '../../stores/transcriptionStore';

interface EditorProps {
  segments: Segment[];
  speakers: Speaker[];
  onSegmentUpdate: (segmentId: string, text: string) => void;
  onSeekToSegment: (segmentId: string) => void;
}

export function Editor({
  segments,
  speakers,
  onSegmentUpdate,
  onSeekToSegment,
}: EditorProps) {
  const { activeSegmentId, currentTime } = useTranscriptionStore();
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const activeRef = useRef<HTMLDivElement>(null);

  const speakerMap = speakers.reduce(
    (acc, s) => ({ ...acc, [s.id]: s }),
    {} as Record<string, Speaker>
  );

  // アクティブセグメントにスクロール
  useEffect(() => {
    if (activeSegmentId && activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [activeSegmentId]);

  const startEditing = (segment: Segment) => {
    setEditingSegmentId(segment.id);
    setEditText(segment.text);
  };

  const saveEdit = () => {
    if (editingSegmentId && editText.trim()) {
      onSegmentUpdate(editingSegmentId, editText.trim());
    }
    setEditingSegmentId(null);
    setEditText('');
  };

  const cancelEdit = () => {
    setEditingSegmentId(null);
    setEditText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      saveEdit();
    } else if (e.key === 'Escape') {
      cancelEdit();
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-2">
        {segments.map((segment) => {
          const speaker = segment.speaker_id
            ? speakerMap[segment.speaker_id]
            : null;
          const isActive = segment.id === activeSegmentId;
          const isEditing = segment.id === editingSegmentId;

          return (
            <div
              key={segment.id}
              ref={isActive ? activeRef : null}
              className={cn(
                'group p-4 rounded-lg transition-colors',
                isActive ? 'bg-primary-50 border border-primary-200' : 'hover:bg-gray-50',
                isEditing && 'bg-yellow-50 border border-yellow-200'
              )}
            >
              {/* タイムスタンプと話者 */}
              <div className="flex items-center gap-2 mb-2">
                <button
                  onClick={() => onSeekToSegment(segment.id)}
                  className="text-xs font-mono text-gray-500 hover:text-primary-600"
                >
                  {formatTimestamp(segment.start_time_ms)}
                </button>
                {speaker && (
                  <span
                    className="px-2 py-0.5 text-xs font-medium rounded-full"
                    style={{
                      backgroundColor: speaker.color || '#e5e7eb',
                      color: speaker.color ? '#fff' : '#374151',
                    }}
                  >
                    {speaker.label}
                  </span>
                )}
                {segment.is_edited && (
                  <span className="text-xs text-gray-400">(編集済み)</span>
                )}
              </div>

              {/* テキスト */}
              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="w-full p-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    rows={3}
                    autoFocus
                  />
                  <div className="flex items-center gap-2 text-sm">
                    <button
                      onClick={saveEdit}
                      className="flex items-center gap-1 px-3 py-1 bg-primary-600 text-white rounded hover:bg-primary-700"
                    >
                      <Check className="w-4 h-4" />
                      保存 (Ctrl+Enter)
                    </button>
                    <button
                      onClick={cancelEdit}
                      className="flex items-center gap-1 px-3 py-1 text-gray-600 hover:bg-gray-100 rounded"
                    >
                      <X className="w-4 h-4" />
                      キャンセル
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-gray-800 leading-relaxed">
                    {segment.text}
                  </p>
                  <button
                    onClick={() => startEditing(segment)}
                    className="p-1.5 text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="編集"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
