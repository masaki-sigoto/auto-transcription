import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key,
  Plus,
  Copy,
  Eye,
  EyeOff,
  Trash2,
  Code,
  Book,
  Terminal,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../lib/api';

interface APIKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

interface APIKeyCreated {
  api_key: APIKey;
  secret_key: string;
}

export default function Developer() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>([]);
  const [newKeyExpires, setNewKeyExpires] = useState<number | null>(null);
  const [createdKey, setCreatedKey] = useState<APIKeyCreated | null>(null);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'keys' | 'docs' | 'examples'>('keys');

  const { data: apiKeys, isLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: async () => {
      const response = await api.get('/developer/api-keys');
      return response.data as APIKey[];
    },
  });

  const { data: apiInfo } = useQuery({
    queryKey: ['api-info'],
    queryFn: async () => {
      const response = await api.get('/developer/docs/info');
      return response.data;
    },
  });

  const { data: codeExamples } = useQuery({
    queryKey: ['code-examples'],
    queryFn: async () => {
      const response = await api.get('/developer/docs/examples');
      return response.data;
    },
  });

  const createKeyMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/developer/api-keys', {
        name: newKeyName,
        scopes: newKeyScopes,
        expires_days: newKeyExpires,
      });
      return response.data as APIKeyCreated;
    },
    onSuccess: (data) => {
      setCreatedKey(data);
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      setNewKeyName('');
      setNewKeyScopes([]);
      setNewKeyExpires(null);
    },
  });

  const deleteKeyMutation = useMutation({
    mutationFn: async (keyId: string) => {
      await api.delete(`/developer/api-keys/${keyId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  const copyToClipboard = async (text: string, id?: string) => {
    await navigator.clipboard.writeText(text);
    if (id) {
      setCopiedKeyId(id);
      setTimeout(() => setCopiedKeyId(null), 2000);
    }
  };

  const availableScopes = [
    { id: 'transcriptions:read', label: '文字起こし読み取り' },
    { id: 'transcriptions:write', label: '文字起こし書き込み' },
    { id: 'upload', label: 'ファイルアップロード' },
    { id: 'ai', label: 'AI機能' },
    { id: 'analytics:read', label: '分析データ読み取り' },
    { id: 'webhooks', label: 'Webhook管理' },
  ];

  const toggleScope = (scope: string) => {
    setNewKeyScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">開発者向け</h1>
        <p className="mt-1 text-gray-600">
          APIキーの管理とドキュメントの確認ができます
        </p>
      </div>

      {/* タブ */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab('keys')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'keys'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Key className="h-4 w-4 inline-block mr-2" />
            APIキー
          </button>
          <button
            onClick={() => setActiveTab('docs')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'docs'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Book className="h-4 w-4 inline-block mr-2" />
            ドキュメント
          </button>
          <button
            onClick={() => setActiveTab('examples')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'examples'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Code className="h-4 w-4 inline-block mr-2" />
            サンプルコード
          </button>
        </nav>
      </div>

      {/* APIキータブ */}
      {activeTab === 'keys' && (
        <div>
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold text-gray-900">APIキー</h2>
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="h-5 w-5 mr-2" />
              新しいキーを作成
            </button>
          </div>

          {/* 警告 */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-yellow-800">APIキーの取り扱いに注意</p>
                <p className="text-sm text-yellow-700 mt-1">
                  APIキーは機密情報です。コードに直接記載したり、公開リポジトリにコミットしないでください。
                </p>
              </div>
            </div>
          </div>

          {/* キー一覧 */}
          <div className="bg-white rounded-lg border border-gray-200">
            {isLoading ? (
              <div className="p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
              </div>
            ) : apiKeys && apiKeys.length > 0 ? (
              <div className="divide-y divide-gray-200">
                {apiKeys.map((key) => (
                  <div key={key.id} className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-medium text-gray-900">{key.name}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <code className="text-sm bg-gray-100 px-2 py-0.5 rounded">
                            {key.key_prefix}...
                          </code>
                          {key.scopes.length > 0 && (
                            <span className="text-xs text-gray-500">
                              {key.scopes.length}個のスコープ
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          作成日: {new Date(key.created_at).toLocaleDateString()}
                          {key.last_used_at && (
                            <> · 最終使用: {new Date(key.last_used_at).toLocaleDateString()}</>
                          )}
                        </p>
                      </div>
                      <button
                        onClick={() => deleteKeyMutation.mutate(key.id)}
                        className="p-2 text-gray-400 hover:text-red-600"
                      >
                        <Trash2 className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-gray-500">
                <Key className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                <p>APIキーがありません</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ドキュメントタブ */}
      {activeTab === 'docs' && apiInfo && (
        <div className="space-y-8">
          {/* 概要 */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">API概要</h2>
            <dl className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm text-gray-500">名前</dt>
                <dd className="font-medium">{apiInfo.name}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">バージョン</dt>
                <dd className="font-medium">{apiInfo.version}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-sm text-gray-500">ベースURL</dt>
                <dd className="font-mono bg-gray-100 px-2 py-1 rounded text-sm">
                  {apiInfo.base_url}
                </dd>
              </div>
            </dl>
          </div>

          {/* 認証 */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">認証</h2>
            <p className="text-gray-600 mb-4">{apiInfo.authentication.description}</p>
            <div className="bg-gray-50 rounded p-4">
              <code className="text-sm">
                {apiInfo.authentication.header}: your-api-key
              </code>
            </div>
          </div>

          {/* エンドポイント */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">主要エンドポイント</h2>
            <div className="space-y-4">
              {Object.entries(apiInfo.endpoints).map(([category, endpoints]: [string, any]) => (
                <div key={category}>
                  <h3 className="font-medium text-gray-700 mb-2 capitalize">{category}</h3>
                  <div className="bg-gray-50 rounded p-4 space-y-2">
                    {Object.entries(endpoints).map(([name, endpoint]: [string, any]) => (
                      <div key={name} className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 w-32">{name}:</span>
                        <code className="text-sm">{endpoint}</code>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* レート制限 */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">レート制限</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-4">プラン</th>
                    <th className="text-left py-2 px-4">リクエスト/分</th>
                    <th className="text-left py-2 px-4">リクエスト/日</th>
                    <th className="text-left py-2 px-4">最大ファイルサイズ</th>
                    <th className="text-left py-2 px-4">最大録音時間</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(apiInfo.rate_limits).map(([plan, limits]: [string, any]) => (
                    <tr key={plan} className="border-b">
                      <td className="py-2 px-4 capitalize font-medium">{plan}</td>
                      <td className="py-2 px-4">{limits.requests_per_minute}</td>
                      <td className="py-2 px-4">{limits.requests_per_day}</td>
                      <td className="py-2 px-4">{limits.max_file_size_mb}MB</td>
                      <td className="py-2 px-4">{limits.max_duration_minutes}分</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* サンプルコードタブ */}
      {activeTab === 'examples' && codeExamples && (
        <div className="space-y-6">
          {Object.entries(codeExamples).map(([lang, examples]: [string, any]) => (
            <div key={lang} className="bg-white rounded-lg border border-gray-200">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900 capitalize">
                  {lang === 'curl' ? 'cURL' : lang}
                </h2>
              </div>
              <div className="divide-y divide-gray-200">
                {Object.entries(examples).map(([name, code]: [string, any]) => (
                  <div key={name} className="p-6">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-medium text-gray-700">{name}</h3>
                      <button
                        onClick={() => copyToClipboard(code, `${lang}-${name}`)}
                        className="text-gray-400 hover:text-gray-600"
                      >
                        {copiedKeyId === `${lang}-${name}` ? (
                          <Check className="h-4 w-4 text-green-500" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto text-sm">
                      <code>{code.trim()}</code>
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* キー作成モーダル */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-4">新しいAPIキーを作成</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  名前
                </label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  placeholder="例: Production API Key"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  スコープ
                </label>
                <div className="space-y-2">
                  {availableScopes.map((scope) => (
                    <label key={scope.id} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={newKeyScopes.includes(scope.id)}
                        onChange={() => toggleScope(scope.id)}
                        className="rounded border-gray-300 text-blue-600"
                      />
                      <span className="ml-2 text-sm text-gray-700">{scope.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  有効期限
                </label>
                <select
                  value={newKeyExpires || ''}
                  onChange={(e) => setNewKeyExpires(e.target.value ? Number(e.target.value) : null)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="">無期限</option>
                  <option value="30">30日</option>
                  <option value="90">90日</option>
                  <option value="365">1年</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => {
                    createKeyMutation.mutate();
                    setShowCreateModal(false);
                  }}
                  disabled={!newKeyName}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  作成
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* キー作成完了モーダル */}
      {createdKey && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-green-100 rounded-full">
                <Check className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold">APIキーが作成されました</h3>
            </div>
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
              <p className="text-sm text-yellow-800">
                このキーは一度だけ表示されます。安全な場所に保存してください。
              </p>
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                シークレットキー
              </label>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono break-all">
                  {createdKey.secret_key}
                </code>
                <button
                  onClick={() => copyToClipboard(createdKey.secret_key, 'new-key')}
                  className="p-2 text-gray-500 hover:text-gray-700"
                >
                  {copiedKeyId === 'new-key' ? (
                    <Check className="h-5 w-5 text-green-500" />
                  ) : (
                    <Copy className="h-5 w-5" />
                  )}
                </button>
              </div>
            </div>
            <button
              onClick={() => setCreatedKey(null)}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              閉じる
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
