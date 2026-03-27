import { useRef, useState, useCallback, useEffect } from 'react';
import { useTranscriptionStore } from '../stores/transcriptionStore';

export function useAudioPlayer(audioUrl: string | null) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [duration, setDuration] = useState(0);
  const [isReady, setIsReady] = useState(false);

  const {
    currentTime,
    isPlaying,
    setCurrentTime,
    setIsPlaying,
    setActiveSegmentId,
    currentTranscription,
  } = useTranscriptionStore();

  // 音声要素の初期化
  useEffect(() => {
    if (!audioUrl) return;

    const audio = new Audio(audioUrl);
    audioRef.current = audio;

    audio.addEventListener('loadedmetadata', () => {
      setDuration(audio.duration);
      setIsReady(true);
    });

    audio.addEventListener('timeupdate', () => {
      setCurrentTime(audio.currentTime * 1000);
    });

    audio.addEventListener('ended', () => {
      setIsPlaying(false);
    });

    return () => {
      audio.pause();
      audio.src = '';
    };
  }, [audioUrl, setCurrentTime, setIsPlaying]);

  // アクティブセグメントの更新
  useEffect(() => {
    if (!currentTranscription?.segments) return;

    const activeSegment = currentTranscription.segments.find(
      (seg) =>
        currentTime >= seg.start_time_ms && currentTime < seg.end_time_ms
    );

    setActiveSegmentId(activeSegment?.id || null);
  }, [currentTime, currentTranscription, setActiveSegmentId]);

  // 再生/一時停止
  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play();
      setIsPlaying(true);
    }
  }, [isPlaying, setIsPlaying]);

  // シーク
  const seek = useCallback((timeMs: number) => {
    const audio = audioRef.current;
    if (!audio) return;

    audio.currentTime = timeMs / 1000;
    setCurrentTime(timeMs);
  }, [setCurrentTime]);

  // 特定のセグメントに移動
  const seekToSegment = useCallback((segmentId: string) => {
    if (!currentTranscription?.segments) return;

    const segment = currentTranscription.segments.find(
      (seg) => seg.id === segmentId
    );

    if (segment) {
      seek(segment.start_time_ms);
    }
  }, [currentTranscription, seek]);

  // 早送り/巻き戻し
  const skip = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;

    const newTime = Math.max(0, Math.min(audio.duration, audio.currentTime + seconds));
    audio.currentTime = newTime;
    setCurrentTime(newTime * 1000);
  }, [setCurrentTime]);

  return {
    audioRef,
    duration,
    currentTime,
    isPlaying,
    isReady,
    togglePlay,
    seek,
    seekToSegment,
    skip,
  };
}
