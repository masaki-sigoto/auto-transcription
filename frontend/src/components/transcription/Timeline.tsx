import { useMemo } from 'react';
import type { Segment, Speaker } from '../../types';
import { cn, formatTimestamp } from '../../lib/utils';
import { useTranscriptionStore } from '../../stores/transcriptionStore';

interface TimelineProps {
  segments: Segment[];
  speakers: Speaker[];
  duration: number; // milliseconds
  onSeek: (timeMs: number) => void;
}

export function Timeline({
  segments,
  speakers,
  duration,
  onSeek,
}: TimelineProps) {
  const { currentTime, activeSegmentId } = useTranscriptionStore();

  const speakerMap = useMemo(
    () =>
      speakers.reduce(
        (acc, s) => ({ ...acc, [s.id]: s }),
        {} as Record<string, Speaker>
      ),
    [speakers]
  );

  // タイムラインブロックを生成
  const timelineBlocks = useMemo(() => {
    if (duration === 0) return [];

    return segments.map((segment) => {
      const startPercent = (segment.start_time_ms / duration) * 100;
      const widthPercent =
        ((segment.end_time_ms - segment.start_time_ms) / duration) * 100;
      const speaker = segment.speaker_id ? speakerMap[segment.speaker_id] : null;

      return {
        segment,
        startPercent,
        widthPercent,
        speaker,
      };
    });
  }, [segments, duration, speakerMap]);

  // 現在位置のパーセント
  const currentPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = x / rect.width;
    const timeMs = percent * duration;
    onSeek(timeMs);
  };

  return (
    <div className="bg-white border-t border-gray-200 p-4">
      <div className="max-w-4xl mx-auto">
        {/* 時間ラベル */}
        <div className="flex justify-between text-xs text-gray-500 mb-2">
          <span>0:00</span>
          <span>{formatTimestamp(duration / 2)}</span>
          <span>{formatTimestamp(duration)}</span>
        </div>

        {/* タイムライン */}
        <div
          className="relative h-16 bg-gray-100 rounded-lg cursor-pointer overflow-hidden"
          onClick={handleClick}
        >
          {/* セグメントブロック */}
          {timelineBlocks.map(({ segment, startPercent, widthPercent, speaker }) => (
            <div
              key={segment.id}
              className={cn(
                'absolute top-2 bottom-2 rounded transition-opacity',
                segment.id === activeSegmentId
                  ? 'ring-2 ring-primary-500 ring-offset-1'
                  : 'hover:opacity-80'
              )}
              style={{
                left: `${startPercent}%`,
                width: `${Math.max(widthPercent, 0.5)}%`,
                backgroundColor: speaker?.color || '#94a3b8',
              }}
              title={`${formatTimestamp(segment.start_time_ms)} - ${segment.text.slice(0, 50)}...`}
            />
          ))}

          {/* 現在位置インジケーター */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-10"
            style={{ left: `${currentPercent}%` }}
          >
            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-3 h-3 bg-red-500 rounded-full" />
          </div>
        </div>

        {/* 話者凡例 */}
        {speakers.length > 0 && (
          <div className="flex gap-4 mt-3">
            {speakers.map((speaker) => (
              <div key={speaker.id} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: speaker.color || '#94a3b8' }}
                />
                <span className="text-xs text-gray-600">{speaker.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
