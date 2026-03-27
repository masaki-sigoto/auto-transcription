import { Play, Pause, SkipBack, SkipForward, Volume2 } from 'lucide-react';
import { formatTimestamp } from '../../lib/utils';
import { cn } from '../../lib/utils';

interface AudioPlayerProps {
  duration: number;
  currentTime: number;
  isPlaying: boolean;
  isReady: boolean;
  onTogglePlay: () => void;
  onSeek: (timeMs: number) => void;
  onSkip: (seconds: number) => void;
}

export function AudioPlayer({
  duration,
  currentTime,
  isPlaying,
  isReady,
  onTogglePlay,
  onSeek,
  onSkip,
}: AudioPlayerProps) {
  const progress = duration > 0 ? (currentTime / (duration * 1000)) * 100 : 0;

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    const timeMs = percentage * duration * 1000;
    onSeek(timeMs);
  };

  return (
    <div className="bg-white border-t border-gray-200 px-6 py-4">
      <div className="max-w-4xl mx-auto">
        {/* プログレスバー */}
        <div
          className="relative h-2 bg-gray-200 rounded-full cursor-pointer mb-4 group"
          onClick={handleSeek}
        >
          <div
            className="absolute h-full bg-primary-500 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
          <div
            className="absolute w-4 h-4 bg-primary-500 rounded-full -top-1 -ml-2 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `${progress}%` }}
          />
        </div>

        <div className="flex items-center justify-between">
          {/* 時間表示 */}
          <div className="text-sm text-gray-500 w-24">
            {formatTimestamp(currentTime)} / {formatTimestamp(duration * 1000)}
          </div>

          {/* コントロールボタン */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onSkip(-10)}
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-full"
              title="10秒戻る"
            >
              <SkipBack className="w-5 h-5" />
            </button>

            <button
              onClick={onTogglePlay}
              disabled={!isReady}
              className={cn(
                'p-3 rounded-full transition-colors',
                isReady
                  ? 'bg-primary-600 text-white hover:bg-primary-700'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              )}
            >
              {isPlaying ? (
                <Pause className="w-6 h-6" />
              ) : (
                <Play className="w-6 h-6 ml-0.5" />
              )}
            </button>

            <button
              onClick={() => onSkip(10)}
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-full"
              title="10秒進む"
            >
              <SkipForward className="w-5 h-5" />
            </button>
          </div>

          {/* 音量（プレースホルダー） */}
          <div className="w-24 flex justify-end">
            <button className="p-2 text-gray-400 hover:text-gray-600">
              <Volume2 className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
