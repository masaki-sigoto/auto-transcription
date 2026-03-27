import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { transcriptionApi } from '../lib/api';
import type { CreateTranscriptionRequest, ExportRequest } from '../types';

export function useTranscriptions(page = 1, perPage = 20) {
  return useQuery({
    queryKey: ['transcriptions', page, perPage],
    queryFn: () => transcriptionApi.list(page, perPage),
  });
}

export function useTranscription(id: string) {
  return useQuery({
    queryKey: ['transcription', id],
    queryFn: () => transcriptionApi.get(id),
    enabled: !!id,
  });
}

export function useCreateTranscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CreateTranscriptionRequest) =>
      transcriptionApi.create(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcriptions'] });
    },
  });
}

export function useUpdateTranscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: { title?: string } }) =>
      transcriptionApi.update(id, updates),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['transcription', id] });
      queryClient.invalidateQueries({ queryKey: ['transcriptions'] });
    },
  });
}

export function useDeleteTranscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => transcriptionApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcriptions'] });
    },
  });
}

export function useUpdateSegment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      segmentId,
      updates,
    }: {
      segmentId: string;
      updates: { text?: string; speaker_id?: string };
    }) => transcriptionApi.updateSegment(segmentId, updates),
    onSuccess: (_, { segmentId }) => {
      // 現在の詳細ページのキャッシュを無効化
      queryClient.invalidateQueries({ queryKey: ['transcription'] });
    },
  });
}

export function useExportTranscription() {
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: ExportRequest }) =>
      transcriptionApi.export(id, request),
  });
}

export function useSummarizeTranscription() {
  return useMutation({
    mutationFn: (id: string) => transcriptionApi.summarize(id),
  });
}
