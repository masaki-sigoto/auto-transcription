import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Plus,
  Search,
  Edit2,
  Trash2,
  Upload,
  Download,
  X,
  Tag,
} from 'lucide-react';
import { api } from '../lib/api';

interface Dictionary {
  id: string;
  name: string;
  description: string | null;
  language: string;
  is_active: boolean;
  is_shared: boolean;
  word_count: number;
  usage_count: number;
  created_at: string;
}

interface Word {
  id: string;
  word: string;
  reading: string | null;
  pronunciation: string | null;
  aliases: string[];
  category: string | null;
  tags: string[];
  priority: number;
  boost_factor: number;
  notes: string | null;
  created_at: string;
}

export default function Vocabulary() {
  const queryClient = useQueryClient();
  const [selectedDictionary, setSelectedDictionary] = useState<Dictionary | null>(null);
  const [showCreateDictModal, setShowCreateDictModal] = useState(false);
  const [showAddWordModal, setShowAddWordModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // 辞書フォーム
  const [dictName, setDictName] = useState('');
  const [dictDescription, setDictDescription] = useState('');
  const [dictLanguage, setDictLanguage] = useState('ja');

  // ワードフォーム
  const [wordForm, setWordForm] = useState({
    word: '',
    reading: '',
    pronunciation: '',
    aliases: '',
    category: '',
    tags: '',
    priority: 0,
    boost_factor: 1.0,
    notes: '',
  });

  const { data: dictionaries, isLoading } = useQuery({
    queryKey: ['dictionaries'],
    queryFn: async () => {
      const response = await api.get('/vocabulary/dictionaries');
      return response.data as Dictionary[];
    },
  });

  const { data: words } = useQuery({
    queryKey: ['words', selectedDictionary?.id, searchQuery],
    queryFn: async () => {
      if (!selectedDictionary) return [];
      const params = new URLSearchParams();
      if (searchQuery) params.append('query', searchQuery);
      const response = await api.get(
        `/vocabulary/dictionaries/${selectedDictionary.id}/words?${params}`
      );
      return response.data as Word[];
    },
    enabled: !!selectedDictionary,
  });

  const createDictMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/vocabulary/dictionaries', {
        name: dictName,
        description: dictDescription || null,
        language: dictLanguage,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
      setShowCreateDictModal(false);
      setDictName('');
      setDictDescription('');
    },
  });

  const deleteDictMutation = useMutation({
    mutationFn: async (dictId: string) => {
      await api.delete(`/vocabulary/dictionaries/${dictId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
      setSelectedDictionary(null);
    },
  });

  const addWordMutation = useMutation({
    mutationFn: async () => {
      if (!selectedDictionary) return;
      const response = await api.post(
        `/vocabulary/dictionaries/${selectedDictionary.id}/words`,
        {
          word: wordForm.word,
          reading: wordForm.reading || null,
          pronunciation: wordForm.pronunciation || null,
          aliases: wordForm.aliases
            .split(',')
            .map((a) => a.trim())
            .filter(Boolean),
          category: wordForm.category || null,
          tags: wordForm.tags
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean),
          priority: wordForm.priority,
          boost_factor: wordForm.boost_factor,
          notes: wordForm.notes || null,
        }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['words'] });
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
      setShowAddWordModal(false);
      setWordForm({
        word: '',
        reading: '',
        pronunciation: '',
        aliases: '',
        category: '',
        tags: '',
        priority: 0,
        boost_factor: 1.0,
        notes: '',
      });
    },
  });

  const deleteWordMutation = useMutation({
    mutationFn: async (wordId: string) => {
      await api.delete(`/vocabulary/words/${wordId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['words'] });
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
    },
  });

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedDictionary) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      await api.post(
        `/vocabulary/dictionaries/${selectedDictionary.id}/words/import`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      queryClient.invalidateQueries({ queryKey: ['words'] });
      queryClient.invalidateQueries({ queryKey: ['dictionaries'] });
    } catch (error) {
      console.error('Import failed:', error);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">カスタム語彙</h1>
          <p className="mt-1 text-gray-600">
            専門用語や固有名詞を登録して、文字起こし精度を向上させます
          </p>
        </div>
        <button
          onClick={() => setShowCreateDictModal(true)}
          className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-5 w-5 mr-2" />
          新しい辞書
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 辞書一覧 */}
        <div className="lg:col-span-1 space-y-4">
          {dictionaries && dictionaries.length > 0 ? (
            dictionaries.map((dict) => (
              <div
                key={dict.id}
                onClick={() => setSelectedDictionary(dict)}
                className={`bg-white rounded-lg border p-4 cursor-pointer transition-colors ${
                  selectedDictionary?.id === dict.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-purple-100 rounded-lg">
                      <BookOpen className="h-5 w-5 text-purple-600" />
                    </div>
                    <div>
                      <h3 className="font-medium text-gray-900">{dict.name}</h3>
                      <p className="text-sm text-gray-500">
                        {dict.word_count}語 · {dict.language.toUpperCase()}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${
                      dict.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {dict.is_active ? '有効' : '無効'}
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div className="bg-gray-50 rounded-lg p-6 text-center">
              <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">辞書がありません</p>
              <button
                onClick={() => setShowCreateDictModal(true)}
                className="mt-4 text-blue-600 hover:text-blue-700 text-sm font-medium"
              >
                辞書を作成する
              </button>
            </div>
          )}
        </div>

        {/* 辞書詳細・ワード一覧 */}
        <div className="lg:col-span-2">
          {selectedDictionary ? (
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900">
                      {selectedDictionary.name}
                    </h2>
                    {selectedDictionary.description && (
                      <p className="mt-1 text-gray-600">
                        {selectedDictionary.description}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    <label className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 cursor-pointer">
                      <Upload className="h-4 w-4 mr-2" />
                      インポート
                      <input
                        type="file"
                        accept=".csv"
                        onChange={handleImport}
                        className="hidden"
                      />
                    </label>
                    <button
                      onClick={() => setShowAddWordModal(true)}
                      className="inline-flex items-center px-3 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      語句を追加
                    </button>
                    <button
                      onClick={() => deleteDictMutation.mutate(selectedDictionary.id)}
                      className="p-2 text-gray-400 hover:text-red-600"
                    >
                      <Trash2 className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {/* 検索 */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="語句を検索..."
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
              </div>

              {/* ワード一覧 */}
              <div className="divide-y divide-gray-100 max-h-[500px] overflow-y-auto">
                {words && words.length > 0 ? (
                  words.map((word) => (
                    <div
                      key={word.id}
                      className="p-4 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="font-medium text-gray-900">
                              {word.word}
                            </span>
                            {word.reading && (
                              <span className="text-sm text-gray-500">
                                ({word.reading})
                              </span>
                            )}
                            {word.category && (
                              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                                {word.category}
                              </span>
                            )}
                          </div>
                          {word.aliases.length > 0 && (
                            <p className="text-sm text-gray-500 mt-1">
                              別名: {word.aliases.join(', ')}
                            </p>
                          )}
                          {word.tags.length > 0 && (
                            <div className="flex items-center space-x-1 mt-1">
                              <Tag className="h-3 w-3 text-gray-400" />
                              {word.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="text-xs text-blue-600"
                                >
                                  #{tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => deleteWordMutation.mutate(word.id)}
                          className="p-1 text-gray-400 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-8 text-center text-gray-500">
                    語句がありません
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg p-12 text-center">
              <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">辞書を選択してください</p>
            </div>
          )}
        </div>
      </div>

      {/* 辞書作成モーダル */}
      {showCreateDictModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">新しい辞書を作成</h3>
              <button
                onClick={() => setShowCreateDictModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  辞書名
                </label>
                <input
                  type="text"
                  value={dictName}
                  onChange={(e) => setDictName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  placeholder="例: 社内用語辞書"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  言語
                </label>
                <select
                  value={dictLanguage}
                  onChange={(e) => setDictLanguage(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="ja">日本語</option>
                  <option value="en">英語</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  説明（任意）
                </label>
                <textarea
                  value={dictDescription}
                  onChange={(e) => setDictDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  rows={2}
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowCreateDictModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => createDictMutation.mutate()}
                  disabled={!dictName}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  作成
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ワード追加モーダル */}
      {showAddWordModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">語句を追加</h3>
              <button
                onClick={() => setShowAddWordModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    語句 *
                  </label>
                  <input
                    type="text"
                    value={wordForm.word}
                    onChange={(e) =>
                      setWordForm({ ...wordForm, word: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md"
                    placeholder="例: ChatGPT"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    読み
                  </label>
                  <input
                    type="text"
                    value={wordForm.reading}
                    onChange={(e) =>
                      setWordForm({ ...wordForm, reading: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md"
                    placeholder="例: チャットジーピーティー"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  別名（カンマ区切り）
                </label>
                <input
                  type="text"
                  value={wordForm.aliases}
                  onChange={(e) =>
                    setWordForm({ ...wordForm, aliases: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  placeholder="例: GPT, ジーピーティー"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    カテゴリ
                  </label>
                  <input
                    type="text"
                    value={wordForm.category}
                    onChange={(e) =>
                      setWordForm({ ...wordForm, category: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md"
                    placeholder="例: 製品名"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    タグ（カンマ区切り）
                  </label>
                  <input
                    type="text"
                    value={wordForm.tags}
                    onChange={(e) =>
                      setWordForm({ ...wordForm, tags: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md"
                    placeholder="例: AI, テクノロジー"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  メモ
                </label>
                <textarea
                  value={wordForm.notes}
                  onChange={(e) =>
                    setWordForm({ ...wordForm, notes: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  rows={2}
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowAddWordModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => addWordMutation.mutate()}
                  disabled={!wordForm.word}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  追加
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
