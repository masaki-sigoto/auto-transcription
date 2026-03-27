import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  syncAll,
  getSyncStatus,
  subscribeSyncStatus,
  updatePendingCount,
  SyncStatus,
} from '../lib/syncService';
import {
  getUnsyncedTranscriptions,
  getOfflineRecordings,
  getPendingUploads,
  getStorageUsage,
} from '../lib/database';
import { getStorageUsage as getFileStorageUsage } from '../lib/offlineTranscription';

interface OfflineItem {
  id: string;
  title: string;
  type: 'transcription' | 'recording' | 'upload';
  createdAt: string;
  status: string;
}

export default function OfflineScreen() {
  const [syncStatus, setSyncStatus] = useState<SyncStatus>(getSyncStatus());
  const [offlineItems, setOfflineItems] = useState<OfflineItem[]>([]);
  const [storageUsed, setStorageUsed] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribeSyncStatus(setSyncStatus);
    loadOfflineData();
    return unsubscribe;
  }, []);

  const loadOfflineData = async () => {
    try {
      // 未同期データを取得
      const [transcriptions, recordings, uploads] = await Promise.all([
        getUnsyncedTranscriptions(),
        getOfflineRecordings(),
        getPendingUploads(),
      ]);

      const items: OfflineItem[] = [
        ...transcriptions.map((t) => ({
          id: t.id,
          title: t.title,
          type: 'transcription' as const,
          createdAt: t.created_at,
          status: t.status,
        })),
        ...recordings.map((r) => ({
          id: r.id,
          title: r.title || '録音',
          type: 'recording' as const,
          createdAt: r.created_at,
          status: 'pending',
        })),
        ...uploads.map((u) => ({
          id: u.id,
          title: `アップロード待ち`,
          type: 'upload' as const,
          createdAt: u.created_at,
          status: u.attempts > 0 ? 'error' : 'pending',
        })),
      ];

      setOfflineItems(items.sort((a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      ));

      // ストレージ使用量
      const storage = await getFileStorageUsage();
      setStorageUsed(storage.used);

      // 保留アイテム数を更新
      await updatePendingCount();
    } catch (error) {
      console.error('Failed to load offline data:', error);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadOfflineData();
    setRefreshing(false);
  };

  const handleSync = async () => {
    if (syncStatus.isSyncing) return;

    try {
      await syncAll();
      await loadOfflineData();
      Alert.alert('同期完了', 'データの同期が完了しました');
    } catch (error) {
      Alert.alert('エラー', '同期に失敗しました');
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString('ja-JP', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getTypeIcon = (type: string): keyof typeof Ionicons.glyphMap => {
    switch (type) {
      case 'transcription':
        return 'document-text';
      case 'recording':
        return 'mic';
      case 'upload':
        return 'cloud-upload';
      default:
        return 'help';
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'completed':
        return '#10b981';
      case 'error':
        return '#ef4444';
      default:
        return '#f59e0b';
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>オフラインデータ</Text>
      </View>

      <ScrollView
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {/* 同期ステータス */}
        <View style={styles.syncCard}>
          <View style={styles.syncHeader}>
            <View style={styles.syncStatus}>
              <View
                style={[
                  styles.syncIndicator,
                  {
                    backgroundColor: syncStatus.isSyncing
                      ? '#f59e0b'
                      : syncStatus.error
                      ? '#ef4444'
                      : '#10b981',
                  },
                ]}
              />
              <Text style={styles.syncText}>
                {syncStatus.isSyncing
                  ? '同期中...'
                  : syncStatus.error
                  ? '同期エラー'
                  : '同期済み'}
              </Text>
            </View>

            <TouchableOpacity
              style={[
                styles.syncButton,
                syncStatus.isSyncing && styles.syncButtonDisabled,
              ]}
              onPress={handleSync}
              disabled={syncStatus.isSyncing}
            >
              <Ionicons
                name="sync"
                size={20}
                color={syncStatus.isSyncing ? '#9ca3af' : '#6366f1'}
              />
              <Text
                style={[
                  styles.syncButtonText,
                  syncStatus.isSyncing && styles.syncButtonTextDisabled,
                ]}
              >
                同期
              </Text>
            </TouchableOpacity>
          </View>

          {syncStatus.lastSyncAt && (
            <Text style={styles.lastSync}>
              最終同期: {formatDate(syncStatus.lastSyncAt)}
            </Text>
          )}

          {syncStatus.error && (
            <Text style={styles.errorText}>{syncStatus.error}</Text>
          )}
        </View>

        {/* ストレージ使用量 */}
        <View style={styles.storageCard}>
          <View style={styles.storageHeader}>
            <Ionicons name="folder" size={20} color="#6b7280" />
            <Text style={styles.storageTitle}>ストレージ使用量</Text>
          </View>
          <Text style={styles.storageValue}>{formatBytes(storageUsed)}</Text>
          <View style={styles.storageBar}>
            <View
              style={[
                styles.storageBarFill,
                { width: `${Math.min((storageUsed / (1024 * 1024 * 500)) * 100, 100)}%` },
              ]}
            />
          </View>
        </View>

        {/* 保留中のアイテム */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            保留中のアイテム ({offlineItems.length})
          </Text>

          {offlineItems.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="checkmark-circle" size={48} color="#10b981" />
              <Text style={styles.emptyText}>
                すべてのデータは同期済みです
              </Text>
            </View>
          ) : (
            offlineItems.map((item) => (
              <View key={item.id} style={styles.itemCard}>
                <View style={styles.itemIcon}>
                  <Ionicons
                    name={getTypeIcon(item.type)}
                    size={24}
                    color="#6366f1"
                  />
                </View>
                <View style={styles.itemContent}>
                  <Text style={styles.itemTitle}>{item.title}</Text>
                  <Text style={styles.itemDate}>{formatDate(item.createdAt)}</Text>
                </View>
                <View
                  style={[
                    styles.itemStatus,
                    { backgroundColor: getStatusColor(item.status) + '20' },
                  ]}
                >
                  <View
                    style={[
                      styles.statusDot,
                      { backgroundColor: getStatusColor(item.status) },
                    ]}
                  />
                  <Text
                    style={[
                      styles.statusText,
                      { color: getStatusColor(item.status) },
                    ]}
                  >
                    {item.status === 'pending' ? '保留中' : item.status === 'error' ? 'エラー' : '完了'}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
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
  content: {
    flex: 1,
    padding: 20,
  },
  syncCard: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  syncHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  syncStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  syncIndicator: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  syncText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#111827',
  },
  syncButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#eef2ff',
    borderRadius: 8,
  },
  syncButtonDisabled: {
    backgroundColor: '#f3f4f6',
  },
  syncButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6366f1',
  },
  syncButtonTextDisabled: {
    color: '#9ca3af',
  },
  lastSync: {
    marginTop: 12,
    fontSize: 13,
    color: '#6b7280',
  },
  errorText: {
    marginTop: 8,
    fontSize: 13,
    color: '#ef4444',
  },
  storageCard: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  storageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  storageTitle: {
    fontSize: 14,
    color: '#6b7280',
  },
  storageValue: {
    fontSize: 24,
    fontWeight: '700',
    color: '#111827',
    marginTop: 8,
  },
  storageBar: {
    height: 8,
    backgroundColor: '#e5e7eb',
    borderRadius: 4,
    marginTop: 12,
    overflow: 'hidden',
  },
  storageBarFill: {
    height: '100%',
    backgroundColor: '#6366f1',
    borderRadius: 4,
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#111827',
    marginBottom: 12,
  },
  emptyState: {
    alignItems: 'center',
    padding: 40,
    backgroundColor: 'white',
    borderRadius: 16,
  },
  emptyText: {
    marginTop: 12,
    fontSize: 16,
    color: '#6b7280',
  },
  itemCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
  },
  itemIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#eef2ff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  itemContent: {
    flex: 1,
    marginLeft: 12,
  },
  itemTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: '#111827',
  },
  itemDate: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 2,
  },
  itemStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 6,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '500',
  },
});
