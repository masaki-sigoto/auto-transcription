import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  TextInput,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { OfflineRecorder, processOfflineTranscription } from '../lib/offlineTranscription';

type RecordingState = 'idle' | 'recording' | 'paused' | 'processing';

export default function RecordScreen() {
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [duration, setDuration] = useState(0);
  const [title, setTitle] = useState('');
  const recorderRef = useRef<OfflineRecorder | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    recorderRef.current = new OfflineRecorder();

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const startRecording = async () => {
    try {
      await recorderRef.current?.startRecording();
      setRecordingState('recording');
      setDuration(0);

      // タイマー開始
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } catch (error) {
      Alert.alert('エラー', '録音の開始に失敗しました');
    }
  };

  const pauseRecording = async () => {
    await recorderRef.current?.pauseRecording();
    setRecordingState('paused');

    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
  };

  const resumeRecording = async () => {
    await recorderRef.current?.resumeRecording();
    setRecordingState('recording');

    timerRef.current = setInterval(() => {
      setDuration((prev) => prev + 1);
    }, 1000);
  };

  const stopRecording = async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    setRecordingState('processing');

    try {
      const result = await recorderRef.current?.stopRecording();

      if (result) {
        // オフライン文字起こしを処理
        await processOfflineTranscription(
          result.uri,
          title || `録音 ${new Date().toLocaleString()}`
        );

        Alert.alert(
          '保存完了',
          'オンライン時に文字起こしが処理されます',
          [{ text: 'OK' }]
        );
      }
    } catch (error) {
      Alert.alert('エラー', '録音の保存に失敗しました');
    }

    setRecordingState('idle');
    setDuration(0);
    setTitle('');
  };

  const cancelRecording = () => {
    Alert.alert('確認', '録音をキャンセルしますか？', [
      { text: 'いいえ', style: 'cancel' },
      {
        text: 'はい',
        style: 'destructive',
        onPress: async () => {
          if (timerRef.current) {
            clearInterval(timerRef.current);
          }
          // 録音を破棄
          setRecordingState('idle');
          setDuration(0);
        },
      },
    ]);
  };

  const formatDuration = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>録音</Text>
      </View>

      {/* タイトル入力 */}
      <View style={styles.titleContainer}>
        <TextInput
          style={styles.titleInput}
          placeholder="タイトル（オプション）"
          value={title}
          onChangeText={setTitle}
          editable={recordingState === 'idle'}
        />
      </View>

      {/* 録音時間表示 */}
      <View style={styles.timerContainer}>
        <Text style={styles.timer}>{formatDuration(duration)}</Text>

        {/* 波形アニメーション（録音中） */}
        {recordingState === 'recording' && (
          <View style={styles.waveContainer}>
            {[...Array(5)].map((_, i) => (
              <View
                key={i}
                style={[
                  styles.waveLine,
                  { height: 20 + Math.random() * 40 },
                ]}
              />
            ))}
          </View>
        )}

        {/* ステータス表示 */}
        <Text style={styles.statusText}>
          {recordingState === 'idle' && '録音準備完了'}
          {recordingState === 'recording' && '録音中...'}
          {recordingState === 'paused' && '一時停止中'}
          {recordingState === 'processing' && '処理中...'}
        </Text>
      </View>

      {/* コントロールボタン */}
      <View style={styles.controls}>
        {recordingState === 'idle' && (
          <TouchableOpacity
            style={styles.recordButton}
            onPress={startRecording}
          >
            <Ionicons name="mic" size={48} color="white" />
          </TouchableOpacity>
        )}

        {recordingState === 'recording' && (
          <View style={styles.recordingControls}>
            <TouchableOpacity
              style={styles.controlButton}
              onPress={cancelRecording}
            >
              <Ionicons name="close" size={32} color="#ef4444" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.pauseButton}
              onPress={pauseRecording}
            >
              <Ionicons name="pause" size={48} color="white" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.stopButton}
              onPress={stopRecording}
            >
              <Ionicons name="stop" size={32} color="white" />
            </TouchableOpacity>
          </View>
        )}

        {recordingState === 'paused' && (
          <View style={styles.recordingControls}>
            <TouchableOpacity
              style={styles.controlButton}
              onPress={cancelRecording}
            >
              <Ionicons name="close" size={32} color="#ef4444" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.recordButton}
              onPress={resumeRecording}
            >
              <Ionicons name="mic" size={48} color="white" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.stopButton}
              onPress={stopRecording}
            >
              <Ionicons name="stop" size={32} color="white" />
            </TouchableOpacity>
          </View>
        )}

        {recordingState === 'processing' && (
          <ActivityIndicator size="large" color="#6366f1" />
        )}
      </View>

      {/* 注意書き */}
      <View style={styles.noteContainer}>
        <Ionicons name="information-circle-outline" size={20} color="#6b7280" />
        <Text style={styles.noteText}>
          オフライン時に録音した音声は、オンライン時に自動で文字起こしされます。
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  header: {
    paddingTop: 60,
    paddingHorizontal: 20,
    paddingBottom: 20,
    backgroundColor: 'white',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#111827',
  },
  titleContainer: {
    padding: 20,
  },
  titleInput: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  timerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  timer: {
    fontSize: 64,
    fontWeight: '300',
    color: '#111827',
    fontVariant: ['tabular-nums'],
  },
  waveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 20,
    height: 60,
  },
  waveLine: {
    width: 4,
    backgroundColor: '#6366f1',
    borderRadius: 2,
  },
  statusText: {
    marginTop: 20,
    fontSize: 16,
    color: '#6b7280',
  },
  controls: {
    padding: 40,
    alignItems: 'center',
  },
  recordButton: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#ef4444',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  recordingControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 30,
  },
  controlButton: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#f3f4f6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pauseButton: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#f59e0b',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stopButton: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#6366f1',
    justifyContent: 'center',
    alignItems: 'center',
  },
  noteContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    padding: 20,
    marginHorizontal: 20,
    marginBottom: 40,
    backgroundColor: '#f3f4f6',
    borderRadius: 12,
  },
  noteText: {
    flex: 1,
    fontSize: 14,
    color: '#6b7280',
    lineHeight: 20,
  },
});
