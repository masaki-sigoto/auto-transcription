import { create } from 'zustand';
import type { Transcription, TranscriptionDetail, Segment } from '../types';

interface TranscriptionState {
  // 一覧
  transcriptions: Transcription[];
  totalCount: number;
  currentPage: number;
  isLoading: boolean;
  error: string | null;

  // 詳細
  currentTranscription: TranscriptionDetail | null;
  isDetailLoading: boolean;

  // 音声プレイヤー
  currentTime: number;
  isPlaying: boolean;
  activeSegmentId: string | null;

  // アクション
  setTranscriptions: (transcriptions: Transcription[], total: number) => void;
  setCurrentPage: (page: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setCurrentTranscription: (transcription: TranscriptionDetail | null) => void;
  setDetailLoading: (loading: boolean) => void;
  updateSegment: (segmentId: string, text: string) => void;
  setCurrentTime: (time: number) => void;
  setIsPlaying: (playing: boolean) => void;
  setActiveSegmentId: (id: string | null) => void;
  addTranscription: (transcription: Transcription) => void;
  removeTranscription: (id: string) => void;
}

export const useTranscriptionStore = create<TranscriptionState>((set) => ({
  // 初期状態
  transcriptions: [],
  totalCount: 0,
  currentPage: 1,
  isLoading: false,
  error: null,
  currentTranscription: null,
  isDetailLoading: false,
  currentTime: 0,
  isPlaying: false,
  activeSegmentId: null,

  // アクション
  setTranscriptions: (transcriptions, total) =>
    set({ transcriptions, totalCount: total }),

  setCurrentPage: (page) => set({ currentPage: page }),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  setCurrentTranscription: (transcription) =>
    set({ currentTranscription: transcription }),

  setDetailLoading: (loading) => set({ isDetailLoading: loading }),

  updateSegment: (segmentId, text) =>
    set((state) => {
      if (!state.currentTranscription) return state;
      return {
        currentTranscription: {
          ...state.currentTranscription,
          segments: state.currentTranscription.segments.map((seg) =>
            seg.id === segmentId ? { ...seg, text, is_edited: true } : seg
          ),
        },
      };
    }),

  setCurrentTime: (time) => set({ currentTime: time }),

  setIsPlaying: (playing) => set({ isPlaying: playing }),

  setActiveSegmentId: (id) => set({ activeSegmentId: id }),

  addTranscription: (transcription) =>
    set((state) => ({
      transcriptions: [transcription, ...state.transcriptions],
      totalCount: state.totalCount + 1,
    })),

  removeTranscription: (id) =>
    set((state) => ({
      transcriptions: state.transcriptions.filter((t) => t.id !== id),
      totalCount: state.totalCount - 1,
    })),
}));
