import { useState } from 'react';
import { Users, Edit2, Check, X, Plus } from 'lucide-react';
import type { Speaker } from '../../types';
import { Button } from '../ui/Button';

interface SpeakerManagerProps {
  speakers: Speaker[];
  onUpdate: (speakerId: string, label: string) => void;
  onMerge?: (sourceId: string, targetId: string) => void;
}

const SPEAKER_COLORS = [
  '#FF6B6B',
  '#4ECDC4',
  '#45B7D1',
  '#96CEB4',
  '#FFEAA7',
  '#DDA0DD',
  '#98D8C8',
  '#F7DC6F',
];

export function SpeakerManager({
  speakers,
  onUpdate,
  onMerge,
}: SpeakerManagerProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeSource, setMergeSource] = useState<string | null>(null);

  const startEditing = (speaker: Speaker) => {
    setEditingId(speaker.id);
    setEditLabel(speaker.label);
  };

  const saveEdit = () => {
    if (editingId && editLabel.trim()) {
      onUpdate(editingId, editLabel.trim());
    }
    setEditingId(null);
    setEditLabel('');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditLabel('');
  };

  const handleMerge = (targetId: string) => {
    if (mergeSource && mergeSource !== targetId && onMerge) {
      onMerge(mergeSource, targetId);
      setShowMergeModal(false);
      setMergeSource(null);
    }
  };

  if (speakers.length === 0) {
    return null;
  }

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-gray-500" />
            <h3 className="font-medium text-gray-900">話者</h3>
            <span className="text-sm text-gray-500">({speakers.length}人)</span>
          </div>

          {speakers.length > 1 && onMerge && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowMergeModal(true)}
            >
              話者を統合
            </Button>
          )}
        </div>

        <div className="flex flex-wrap gap-3">
          {speakers.map((speaker) => (
            <div
              key={speaker.id}
              className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg"
            >
              <div
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: speaker.color || '#94a3b8' }}
              />

              {editingId === speaker.id ? (
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    className="w-24 px-2 py-1 text-sm border rounded"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit();
                      if (e.key === 'Escape') cancelEdit();
                    }}
                  />
                  <button
                    onClick={saveEdit}
                    className="p-1 text-green-600 hover:bg-green-50 rounded"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="p-1 text-gray-400 hover:bg-gray-100 rounded"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <>
                  <span className="text-sm font-medium text-gray-700">
                    {speaker.label}
                  </span>
                  <button
                    onClick={() => startEditing(speaker)}
                    className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>

        {/* 話者統合モーダル */}
        {showMergeModal && (
          <>
            <div
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => {
                setShowMergeModal(false);
                setMergeSource(null);
              }}
            />
            <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md bg-white rounded-xl shadow-xl z-50 p-6">
              <h3 className="text-lg font-bold text-gray-900 mb-4">
                話者を統合
              </h3>
              <p className="text-sm text-gray-500 mb-4">
                {mergeSource
                  ? '統合先の話者を選択してください'
                  : '統合元の話者を選択してください'}
              </p>

              <div className="space-y-2">
                {speakers.map((speaker) => (
                  <button
                    key={speaker.id}
                    onClick={() => {
                      if (!mergeSource) {
                        setMergeSource(speaker.id);
                      } else {
                        handleMerge(speaker.id);
                      }
                    }}
                    disabled={mergeSource === speaker.id}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors ${
                      mergeSource === speaker.id
                        ? 'bg-primary-100 border-2 border-primary-500'
                        : 'bg-gray-50 hover:bg-gray-100'
                    }`}
                  >
                    <div
                      className="w-4 h-4 rounded-full"
                      style={{ backgroundColor: speaker.color || '#94a3b8' }}
                    />
                    <span className="font-medium">{speaker.label}</span>
                    {mergeSource === speaker.id && (
                      <span className="ml-auto text-xs text-primary-600">
                        統合元
                      </span>
                    )}
                  </button>
                ))}
              </div>

              <div className="flex justify-end gap-2 mt-6">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowMergeModal(false);
                    setMergeSource(null);
                  }}
                >
                  キャンセル
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
