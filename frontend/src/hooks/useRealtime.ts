import { useState, useRef, useCallback, useEffect } from 'react';

interface RealtimeSegment {
  text: string;
  start_time_ms: number;
  end_time_ms: number;
  is_final: boolean;
  confidence: number | null;
}

interface UseRealtimeOptions {
  language?: string;
  engine?: string;
  onSegment?: (segment: RealtimeSegment) => void;
  onError?: (error: string) => void;
}

export function useRealtime(options: UseRealtimeOptions = {}) {
  const { language = 'ja', engine = 'reazon', onSegment, onError } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [segments, setSegments] = useState<RealtimeSegment[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // WebSocket接続
  const connect = useCallback(() => {
    const wsUrl = `${import.meta.env.VITE_WS_URL || 'ws://localhost:8000'}/api/v1/ws/realtime?language=${language}&engine=${engine}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'session_started':
          setSessionId(data.session_id);
          break;

        case 'transcript':
          const segment = data.segment as RealtimeSegment;
          setSegments((prev) => [...prev, segment]);
          onSegment?.(segment);
          break;

        case 'session_ended':
          setIsRecording(false);
          break;

        case 'error':
          onError?.(data.message);
          break;
      }
    };

    ws.onerror = () => {
      onError?.('WebSocket接続エラーが発生しました');
    };

    ws.onclose = () => {
      setIsConnected(false);
      setSessionId(null);
    };
  }, [language, engine, onSegment, onError]);

  // 録音開始
  const startRecording = useCallback(async () => {
    try {
      // マイクアクセス取得
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // AudioContext設定
      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // 音声データ処理
      processor.onaudioprocess = (event) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          return;
        }

        const inputData = event.inputBuffer.getChannelData(0);

        // Float32 -> Int16 変換
        const int16Data = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Base64エンコードして送信
        const base64 = btoa(
          String.fromCharCode(...new Uint8Array(int16Data.buffer))
        );

        wsRef.current.send(
          JSON.stringify({
            type: 'audio_chunk',
            data: base64,
            sample_rate: 16000,
          })
        );
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      // WebSocket接続
      connect();
      setIsRecording(true);
      setSegments([]);
    } catch (error) {
      onError?.('マイクへのアクセスが許可されていません');
    }
  }, [connect, onError]);

  // 録音停止
  const stopRecording = useCallback(() => {
    // WebSocketに停止通知
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
    }

    // AudioContext停止
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    // MediaStream停止
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // WebSocket切断
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsRecording(false);
  }, []);

  // クリーンアップ
  useEffect(() => {
    return () => {
      stopRecording();
    };
  }, [stopRecording]);

  // 全テキストを取得
  const getFullText = useCallback(() => {
    return segments.map((s) => s.text).join('');
  }, [segments]);

  return {
    isRecording,
    isConnected,
    segments,
    sessionId,
    startRecording,
    stopRecording,
    getFullText,
  };
}
