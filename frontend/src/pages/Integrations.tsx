import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Link2,
  Unlink,
  MessageSquare,
  FileText,
  ChevronRight,
  Video,
  Users,
  CheckSquare,
  Settings,
  X
} from 'lucide-react';
import { api } from '../lib/api';

interface Integration {
  id: string;
  service: string;
  is_active: boolean;
  config: Record<string, string>;
  created_at: string;
}

type TabType = 'all' | 'video' | 'crm' | 'project' | 'other';

// 連携プロバイダーの定義
const integrationProviders = {
  video: [
    {
      id: 'zoom',
      name: 'Zoom',
      description: 'Zoom会議の録画を自動インポート・文字起こし',
      icon: Video,
      color: 'bg-blue-500',
      authType: 'oauth',
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      description: 'Teams会議の録画を自動インポート・文字起こし',
      icon: Video,
      color: 'bg-purple-700',
      authType: 'oauth',
    },
    {
      id: 'meet',
      name: 'Google Meet',
      description: 'Google Meet会議の録画を自動インポート',
      icon: Video,
      color: 'bg-green-600',
      authType: 'oauth',
    },
  ],
  crm: [
    {
      id: 'salesforce',
      name: 'Salesforce',
      description: '商談・連絡先と文字起こしを連携',
      icon: Users,
      color: 'bg-blue-400',
      authType: 'token',
      fields: [
        { key: 'instance_url', label: 'インスタンスURL', placeholder: 'https://your-org.salesforce.com' },
        { key: 'access_token', label: 'アクセストークン', type: 'password' },
      ],
    },
    {
      id: 'hubspot',
      name: 'HubSpot',
      description: 'CRMに会議記録を自動登録',
      icon: Users,
      color: 'bg-orange-500',
      authType: 'token',
      fields: [
        { key: 'access_token', label: 'APIキー', type: 'password' },
      ],
    },
  ],
  project: [
    {
      id: 'jira',
      name: 'Jira',
      description: 'アクションアイテムをJiraタスクとして作成',
      icon: CheckSquare,
      color: 'bg-blue-600',
      authType: 'token',
      fields: [
        { key: 'domain', label: 'ドメイン', placeholder: 'your-org (atlassian.netを除く)' },
        { key: 'email', label: 'メールアドレス' },
        { key: 'api_token', label: 'APIトークン', type: 'password' },
      ],
    },
    {
      id: 'asana',
      name: 'Asana',
      description: 'プロジェクトにタスクをエクスポート',
      icon: CheckSquare,
      color: 'bg-red-400',
      authType: 'token',
      fields: [
        { key: 'access_token', label: 'アクセストークン', type: 'password' },
      ],
    },
    {
      id: 'notion',
      name: 'Notion',
      description: '議事録をNotionページとして作成',
      icon: FileText,
      color: 'bg-gray-900',
      authType: 'oauth',
    },
  ],
  other: [
    {
      id: 'slack',
      name: 'Slack',
      description: '文字起こし完了をSlackチャンネルに通知',
      icon: MessageSquare,
      color: 'bg-purple-600',
      authType: 'oauth',
    },
  ],
};

export default function Integrations() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const [connectDialog, setConnectDialog] = useState<{
    open: boolean;
    provider: any;
  }>({ open: false, provider: null });
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { data: integrations, isLoading } = useQuery({
    queryKey: ['integrations'],
    queryFn: async () => {
      const response = await api.get('/integrations');
      return response.data as Integration[];
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: async (integrationId: string) => {
      await api.delete(`/integrations/${integrationId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations'] });
      setSuccess('連携を解除しました');
    },
  });

  const handleConnect = async (provider: any) => {
    if (provider.authType === 'oauth') {
      try {
        const response = await api.get(`/integrations/${provider.id}/auth`);
        window.location.href = response.data.auth_url;
      } catch (err) {
        console.error('Failed to start auth:', err);
        setError('認証の開始に失敗しました');
      }
    } else {
      setConnectDialog({ open: true, provider });
      setCredentials({});
      setError(null);
    }
  };

  const handleSubmitConnect = async () => {
    if (!connectDialog.provider) return;

    setConnecting(true);
    setError(null);

    try {
      await api.post(`/integrations/config/manual/${connectDialog.provider.id}`, credentials);
      setSuccess(`${connectDialog.provider.name}と連携しました`);
      setConnectDialog({ open: false, provider: null });
      queryClient.invalidateQueries({ queryKey: ['integrations'] });
    } catch (err) {
      setError('連携に失敗しました。認証情報を確認してください。');
    } finally {
      setConnecting(false);
    }
  };

  const getServiceInfo = (service: string) => {
    const allProviders = [
      ...integrationProviders.video,
      ...integrationProviders.crm,
      ...integrationProviders.project,
      ...integrationProviders.other,
    ];
    const found = allProviders.find(p => p.id === service);
    if (found) {
      return found;
    }
    return {
      id: service,
      name: service,
      description: '',
      icon: Link2,
      color: 'bg-gray-500',
    };
  };

  const connectedServices = integrations?.map((i) => i.service) || [];

  const getProvidersForTab = () => {
    if (activeTab === 'all') {
      return [
        ...integrationProviders.video,
        ...integrationProviders.crm,
        ...integrationProviders.project,
        ...integrationProviders.other,
      ];
    }
    return integrationProviders[activeTab] || [];
  };

  const tabs: { id: TabType; label: string; icon: any }[] = [
    { id: 'all', label: 'すべて', icon: Link2 },
    { id: 'video', label: 'ビデオ会議', icon: Video },
    { id: 'crm', label: 'CRM', icon: Users },
    { id: 'project', label: 'プロジェクト管理', icon: CheckSquare },
    { id: 'other', label: 'その他', icon: Settings },
  ];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const providers = getProvidersForTab();

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">外部サービス連携</h1>
        <p className="mt-1 text-gray-600">
          他のサービスと連携して、文字起こしデータを活用しましょう
        </p>
      </div>

      {/* アラート */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <span className="text-red-800">{error}</span>
          <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800">
            <X className="h-5 w-5" />
          </button>
        </div>
      )}

      {success && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg flex items-center justify-between">
          <span className="text-green-800">{success}</span>
          <button onClick={() => setSuccess(null)} className="text-green-600 hover:text-green-800">
            <X className="h-5 w-5" />
          </button>
        </div>
      )}

      {/* タブ */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* 連携済みサービス */}
      {integrations && integrations.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">連携済み</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {integrations.map((integration) => {
              const info = getServiceInfo(integration.service);
              const Icon = info.icon;

              return (
                <div
                  key={integration.id}
                  className="bg-white rounded-lg border-2 border-green-200 p-4"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      <div className={`p-3 rounded-lg ${info.color}`}>
                        <Icon className="h-6 w-6 text-white" />
                      </div>
                      <div>
                        <h3 className="font-medium text-gray-900">{info.name}</h3>
                        <p className="text-sm text-gray-500">
                          {integration.config.workspace_name ||
                            integration.config.team_name ||
                            integration.config.domain ||
                            '接続済み'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        接続中
                      </span>
                      <button
                        onClick={() => disconnectMutation.mutate(integration.id)}
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="連携を解除"
                      >
                        <Unlink className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 利用可能なサービス */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">利用可能な連携</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {providers
            .filter((s) => !connectedServices.includes(s.id))
            .map((service) => {
              const Icon = service.icon;

              return (
                <div
                  key={service.id}
                  className="bg-white rounded-lg border border-gray-200 p-4 hover:border-gray-300 hover:shadow-md transition-all"
                >
                  <div className="flex flex-col h-full">
                    <div className="flex items-center space-x-3 mb-3">
                      <div className={`p-2 rounded-lg ${service.color}`}>
                        <Icon className="h-5 w-5 text-white" />
                      </div>
                      <h3 className="font-medium text-gray-900">{service.name}</h3>
                    </div>
                    <p className="text-sm text-gray-500 mb-4 flex-grow">{service.description}</p>
                    <button
                      onClick={() => handleConnect(service)}
                      className="w-full inline-flex items-center justify-center px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                    >
                      連携する
                      <ChevronRight className="ml-1 h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* 使い方 */}
      <div className="mt-12 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6">
        <h3 className="font-semibold text-blue-900 mb-4">連携でできること</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <Video className="h-5 w-5 text-blue-600" />
              <span className="font-medium text-blue-900">ビデオ会議</span>
            </div>
            <p className="text-sm text-blue-800">
              Zoom、Teams、Meetの録画を自動で文字起こし
            </p>
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <Users className="h-5 w-5 text-blue-600" />
              <span className="font-medium text-blue-900">CRM</span>
            </div>
            <p className="text-sm text-blue-800">
              商談や顧客情報と会議記録を自動連携
            </p>
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <CheckSquare className="h-5 w-5 text-blue-600" />
              <span className="font-medium text-blue-900">プロジェクト管理</span>
            </div>
            <p className="text-sm text-blue-800">
              アクションアイテムをタスクとして自動作成
            </p>
          </div>
        </div>
      </div>

      {/* 連携設定モーダル */}
      {connectDialog.open && connectDialog.provider && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">
                  {connectDialog.provider.name}と連携
                </h3>
                <button
                  onClick={() => setConnectDialog({ open: false, provider: null })}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-4">
                {connectDialog.provider.fields?.map((field: any) => (
                  <div key={field.key}>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      {field.label}
                    </label>
                    <input
                      type={field.type || 'text'}
                      placeholder={field.placeholder}
                      value={credentials[field.key] || ''}
                      onChange={(e) =>
                        setCredentials({ ...credentials, [field.key]: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                ))}
              </div>

              <div className="mt-6 flex justify-end space-x-3">
                <button
                  onClick={() => setConnectDialog({ open: false, provider: null })}
                  className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900"
                >
                  キャンセル
                </button>
                <button
                  onClick={handleSubmitConnect}
                  disabled={connecting}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  {connecting ? '接続中...' : '連携する'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
