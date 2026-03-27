import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Users,
  Plus,
  Settings,
  UserPlus,
  Crown,
  Shield,
  User,
  Eye,
  Trash2,
  X,
} from 'lucide-react';
import { api } from '../lib/api';

interface Team {
  id: string;
  name: string;
  description: string | null;
  members_count: number;
  created_at: string;
}

interface TeamMember {
  id: string;
  user_id: string;
  email: string | null;
  name: string | null;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  joined_at: string;
}

const roleIcons = {
  owner: Crown,
  admin: Shield,
  member: User,
  viewer: Eye,
};

const roleLabels = {
  owner: 'オーナー',
  admin: '管理者',
  member: 'メンバー',
  viewer: '閲覧者',
};

export default function Teams() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDescription, setNewTeamDescription] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'admin' | 'member' | 'viewer'>('member');

  const { data: teams, isLoading } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const response = await api.get('/teams');
      return response.data as Team[];
    },
  });

  const { data: members } = useQuery({
    queryKey: ['team-members', selectedTeam?.id],
    queryFn: async () => {
      if (!selectedTeam) return [];
      const response = await api.get(`/teams/${selectedTeam.id}/members`);
      return response.data as TeamMember[];
    },
    enabled: !!selectedTeam,
  });

  const createTeamMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/teams', {
        name: newTeamName,
        description: newTeamDescription || null,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      setShowCreateModal(false);
      setNewTeamName('');
      setNewTeamDescription('');
    },
  });

  const inviteMutation = useMutation({
    mutationFn: async () => {
      if (!selectedTeam) return;
      const response = await api.post(`/teams/${selectedTeam.id}/invite`, {
        email: inviteEmail,
        role: inviteRole,
      });
      return response.data;
    },
    onSuccess: () => {
      setShowInviteModal(false);
      setInviteEmail('');
      setInviteRole('member');
    },
  });

  const deleteTeamMutation = useMutation({
    mutationFn: async (teamId: string) => {
      await api.delete(`/teams/${teamId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      setSelectedTeam(null);
    },
  });

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
          <h1 className="text-2xl font-bold text-gray-900">チーム</h1>
          <p className="mt-1 text-gray-600">
            チームを作成して文字起こしを共有しましょう
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-5 w-5 mr-2" />
          新しいチーム
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* チーム一覧 */}
        <div className="lg:col-span-1 space-y-4">
          {teams && teams.length > 0 ? (
            teams.map((team) => (
              <div
                key={team.id}
                onClick={() => setSelectedTeam(team)}
                className={`bg-white rounded-lg border p-4 cursor-pointer transition-colors ${
                  selectedTeam?.id === team.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-blue-100 rounded-lg">
                      <Users className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="font-medium text-gray-900">{team.name}</h3>
                      <p className="text-sm text-gray-500">
                        {team.members_count}人のメンバー
                      </p>
                    </div>
                  </div>
                </div>
                {team.description && (
                  <p className="mt-2 text-sm text-gray-600 line-clamp-2">
                    {team.description}
                  </p>
                )}
              </div>
            ))
          ) : (
            <div className="bg-gray-50 rounded-lg p-6 text-center">
              <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">チームがありません</p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-4 text-blue-600 hover:text-blue-700 text-sm font-medium"
              >
                チームを作成する
              </button>
            </div>
          )}
        </div>

        {/* チーム詳細 */}
        <div className="lg:col-span-2">
          {selectedTeam ? (
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900">
                      {selectedTeam.name}
                    </h2>
                    {selectedTeam.description && (
                      <p className="mt-1 text-gray-600">{selectedTeam.description}</p>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => setShowInviteModal(true)}
                      className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                    >
                      <UserPlus className="h-4 w-4 mr-2" />
                      招待
                    </button>
                    <button
                      onClick={() => deleteTeamMutation.mutate(selectedTeam.id)}
                      className="p-2 text-gray-400 hover:text-red-600"
                    >
                      <Trash2 className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* メンバー一覧 */}
              <div className="p-6">
                <h3 className="font-medium text-gray-900 mb-4">メンバー</h3>
                <div className="space-y-3">
                  {members?.map((member) => {
                    const RoleIcon = roleIcons[member.role];
                    return (
                      <div
                        key={member.id}
                        className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0"
                      >
                        <div className="flex items-center space-x-3">
                          <div className="w-10 h-10 bg-gray-200 rounded-full flex items-center justify-center">
                            <User className="h-5 w-5 text-gray-500" />
                          </div>
                          <div>
                            <p className="font-medium text-gray-900">
                              {member.name || member.email || 'Unknown'}
                            </p>
                            <p className="text-sm text-gray-500">{member.email}</p>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            <RoleIcon className="h-3 w-3 mr-1" />
                            {roleLabels[member.role]}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg p-12 text-center">
              <Settings className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">チームを選択してください</p>
            </div>
          )}
        </div>
      </div>

      {/* チーム作成モーダル */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">新しいチームを作成</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  チーム名
                </label>
                <input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                  placeholder="例: マーケティングチーム"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  説明（任意）
                </label>
                <textarea
                  value={newTeamDescription}
                  onChange={(e) => setNewTeamDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                  rows={3}
                  placeholder="チームの説明を入力..."
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => createTeamMutation.mutate()}
                  disabled={!newTeamName}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  作成
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 招待モーダル */}
      {showInviteModal && selectedTeam && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">メンバーを招待</h3>
              <button
                onClick={() => setShowInviteModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  メールアドレス
                </label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                  placeholder="example@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  権限
                </label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as typeof inviteRole)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="admin">管理者</option>
                  <option value="member">メンバー</option>
                  <option value="viewer">閲覧者</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowInviteModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => inviteMutation.mutate()}
                  disabled={!inviteEmail}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  招待を送信
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
