"""高度なユーザー管理サービス - RBAC, MFA, Session, SCIM"""

import os
import uuid
import secrets
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import jwt


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"
    GUEST = "guest"


class Permission(str, Enum):
    # 文字起こし
    TRANSCRIPTION_CREATE = "transcription:create"
    TRANSCRIPTION_READ = "transcription:read"
    TRANSCRIPTION_UPDATE = "transcription:update"
    TRANSCRIPTION_DELETE = "transcription:delete"

    # チーム
    TEAM_CREATE = "team:create"
    TEAM_READ = "team:read"
    TEAM_UPDATE = "team:update"
    TEAM_DELETE = "team:delete"
    TEAM_INVITE = "team:invite"

    # ユーザー管理
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_MANAGE = "user:manage"

    # 設定
    SETTINGS_READ = "settings:read"
    SETTINGS_UPDATE = "settings:update"

    # API
    API_ACCESS = "api:access"
    API_MANAGE = "api:manage"

    # 分析
    ANALYTICS_READ = "analytics:read"
    ANALYTICS_EXPORT = "analytics:export"


ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.ADMIN: list(Permission),  # 全権限
    UserRole.MANAGER: [
        Permission.TRANSCRIPTION_CREATE,
        Permission.TRANSCRIPTION_READ,
        Permission.TRANSCRIPTION_UPDATE,
        Permission.TRANSCRIPTION_DELETE,
        Permission.TEAM_READ,
        Permission.TEAM_UPDATE,
        Permission.TEAM_INVITE,
        Permission.USER_READ,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_UPDATE,
        Permission.API_ACCESS,
        Permission.ANALYTICS_READ,
        Permission.ANALYTICS_EXPORT,
    ],
    UserRole.MEMBER: [
        Permission.TRANSCRIPTION_CREATE,
        Permission.TRANSCRIPTION_READ,
        Permission.TRANSCRIPTION_UPDATE,
        Permission.TEAM_READ,
        Permission.USER_READ,
        Permission.SETTINGS_READ,
        Permission.API_ACCESS,
        Permission.ANALYTICS_READ,
    ],
    UserRole.VIEWER: [
        Permission.TRANSCRIPTION_READ,
        Permission.TEAM_READ,
        Permission.USER_READ,
        Permission.ANALYTICS_READ,
    ],
    UserRole.GUEST: [
        Permission.TRANSCRIPTION_READ,
    ],
}


@dataclass
class Session:
    id: str
    user_id: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
    created_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    is_active: bool = True


@dataclass
class MFAConfig:
    enabled: bool = False
    method: str = "totp"  # totp, sms, email
    secret: Optional[str] = None
    backup_codes: List[str] = field(default_factory=list)
    last_used: Optional[datetime] = None


class SessionService:
    """セッション管理サービス"""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}
        self._jwt_secret = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))

    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None,
        expires_in_hours: int = 24,
    ) -> Session:
        """セッションを作成"""
        session_id = str(uuid.uuid4())
        access_token = self._generate_jwt(user_id, session_id, expires_in_hours)
        refresh_token = secrets.token_urlsafe(32)

        session = Session(
            id=session_id,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
            created_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
        )

        self._sessions[session_id] = session

        # ユーザーセッションリストに追加
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session_id)

        return session

    def _generate_jwt(
        self,
        user_id: str,
        session_id: str,
        expires_in_hours: int,
    ) -> str:
        """JWTを生成"""
        payload = {
            "sub": user_id,
            "session_id": session_id,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=expires_in_hours),
            "type": "access",
        }
        return jwt.encode(payload, self._jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """トークンを検証"""
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            session = self._sessions.get(payload["session_id"])
            if session and session.is_active and session.expires_at > datetime.utcnow():
                return payload
            return None
        except jwt.PyJWTError:
            return None

    def refresh_session(self, refresh_token: str) -> Optional[Session]:
        """セッションをリフレッシュ"""
        for session in self._sessions.values():
            if session.refresh_token == refresh_token and session.is_active:
                session.access_token = self._generate_jwt(
                    session.user_id,
                    session.id,
                    24,
                )
                session.expires_at = datetime.utcnow() + timedelta(hours=24)
                session.refresh_token = secrets.token_urlsafe(32)
                return session
        return None

    def revoke_session(self, session_id: str) -> bool:
        """セッションを無効化"""
        if session_id in self._sessions:
            self._sessions[session_id].is_active = False
            return True
        return False

    def revoke_all_sessions(self, user_id: str) -> int:
        """ユーザーの全セッションを無効化"""
        count = 0
        for session_id in self._user_sessions.get(user_id, []):
            if session_id in self._sessions:
                self._sessions[session_id].is_active = False
                count += 1
        return count

    def get_user_sessions(self, user_id: str) -> List[Session]:
        """ユーザーのアクティブセッション一覧"""
        sessions = []
        for session_id in self._user_sessions.get(user_id, []):
            session = self._sessions.get(session_id)
            if session and session.is_active:
                sessions.append(session)
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        """セッションを取得"""
        session = self._sessions.get(session_id)
        if session and session.is_active:
            return session
        return None


class MFAService:
    """多要素認証サービス"""

    def __init__(self):
        self._mfa_configs: Dict[str, MFAConfig] = {}
        self._pending_setups: Dict[str, str] = {}  # user_id -> secret

    def setup_totp(self, user_id: str, app_name: str = "Transcription App") -> Dict[str, str]:
        """TOTP MFAをセットアップ"""
        try:
            import pyotp
        except ImportError:
            # pyotpがない場合のフォールバック
            secret = secrets.token_hex(20).upper()
            return {
                "secret": secret,
                "provisioning_uri": f"otpauth://totp/{app_name}:{user_id}?secret={secret}&issuer={app_name}",
                "backup_codes": self._generate_backup_codes(),
            }

        secret = pyotp.random_base32()
        self._pending_setups[user_id] = secret

        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user_id,
            issuer_name=app_name,
        )

        backup_codes = self._generate_backup_codes()

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "backup_codes": backup_codes,
        }

    def _generate_backup_codes(self, count: int = 10) -> List[str]:
        """バックアップコードを生成"""
        return [secrets.token_hex(4).upper() for _ in range(count)]

    def verify_totp(self, user_id: str, code: str) -> bool:
        """TOTPコードを検証"""
        try:
            import pyotp
        except ImportError:
            return False

        # セットアップ中の検証
        if user_id in self._pending_setups:
            secret = self._pending_setups[user_id]
            totp = pyotp.TOTP(secret)
            return totp.verify(code)

        # 有効なMFA設定の検証
        config = self._mfa_configs.get(user_id)
        if not config or not config.secret:
            return False

        totp = pyotp.TOTP(config.secret)
        if totp.verify(code):
            config.last_used = datetime.utcnow()
            return True
        return False

    def verify_backup_code(self, user_id: str, code: str) -> bool:
        """バックアップコードを検証"""
        config = self._mfa_configs.get(user_id)
        if not config:
            return False

        if code.upper() in config.backup_codes:
            config.backup_codes.remove(code.upper())
            config.last_used = datetime.utcnow()
            return True
        return False

    def enable_mfa(self, user_id: str, code: str) -> bool:
        """MFAを有効化（コード確認後）"""
        if user_id not in self._pending_setups:
            return False

        if not self.verify_totp(user_id, code):
            return False

        secret = self._pending_setups.pop(user_id)
        self._mfa_configs[user_id] = MFAConfig(
            enabled=True,
            method="totp",
            secret=secret,
            backup_codes=self._generate_backup_codes(),
        )
        return True

    def disable_mfa(self, user_id: str) -> bool:
        """MFAを無効化"""
        if user_id in self._mfa_configs:
            del self._mfa_configs[user_id]
            return True
        return False

    def is_mfa_enabled(self, user_id: str) -> bool:
        """MFAが有効かチェック"""
        config = self._mfa_configs.get(user_id)
        return config is not None and config.enabled

    def get_mfa_status(self, user_id: str) -> Dict[str, Any]:
        """MFAステータスを取得"""
        config = self._mfa_configs.get(user_id)
        if not config:
            return {"enabled": False}

        return {
            "enabled": config.enabled,
            "method": config.method,
            "backup_codes_remaining": len(config.backup_codes),
            "last_used": config.last_used.isoformat() if config.last_used else None,
        }

    def regenerate_backup_codes(self, user_id: str) -> List[str]:
        """バックアップコードを再生成"""
        config = self._mfa_configs.get(user_id)
        if not config:
            return []

        config.backup_codes = self._generate_backup_codes()
        return config.backup_codes


class RBACService:
    """ロールベースアクセス制御サービス"""

    def __init__(self):
        self._user_roles: Dict[str, UserRole] = {}
        self._custom_permissions: Dict[str, List[Permission]] = {}
        self._team_roles: Dict[str, Dict[str, UserRole]] = {}  # team_id -> user_id -> role

    def assign_role(self, user_id: str, role: UserRole) -> None:
        """ロールを割り当て"""
        self._user_roles[user_id] = role

    def get_role(self, user_id: str) -> UserRole:
        """ロールを取得"""
        return self._user_roles.get(user_id, UserRole.MEMBER)

    def assign_team_role(self, team_id: str, user_id: str, role: UserRole) -> None:
        """チームロールを割り当て"""
        if team_id not in self._team_roles:
            self._team_roles[team_id] = {}
        self._team_roles[team_id][user_id] = role

    def get_team_role(self, team_id: str, user_id: str) -> Optional[UserRole]:
        """チームロールを取得"""
        return self._team_roles.get(team_id, {}).get(user_id)

    def has_permission(
        self,
        user_id: str,
        permission: Permission,
        team_id: Optional[str] = None,
    ) -> bool:
        """権限をチェック"""
        # チーム権限をチェック
        if team_id:
            team_role = self.get_team_role(team_id, user_id)
            if team_role:
                team_permissions = ROLE_PERMISSIONS.get(team_role, [])
                if permission in team_permissions:
                    return True

        # グローバルロール権限をチェック
        role = self.get_role(user_id)
        role_permissions = ROLE_PERMISSIONS.get(role, [])
        if permission in role_permissions:
            return True

        # カスタム権限をチェック
        custom = self._custom_permissions.get(user_id, [])
        return permission in custom

    def grant_permission(self, user_id: str, permission: Permission) -> None:
        """カスタム権限を付与"""
        if user_id not in self._custom_permissions:
            self._custom_permissions[user_id] = []
        if permission not in self._custom_permissions[user_id]:
            self._custom_permissions[user_id].append(permission)

    def revoke_permission(self, user_id: str, permission: Permission) -> None:
        """カスタム権限を剥奪"""
        if user_id in self._custom_permissions:
            if permission in self._custom_permissions[user_id]:
                self._custom_permissions[user_id].remove(permission)

    def get_permissions(self, user_id: str) -> List[Permission]:
        """全権限を取得"""
        role = self.get_role(user_id)
        role_permissions = ROLE_PERMISSIONS.get(role, [])
        custom = self._custom_permissions.get(user_id, [])
        return list(set(list(role_permissions) + custom))

    def get_all_roles(self) -> List[Dict[str, Any]]:
        """全ロール一覧を取得"""
        return [
            {
                "id": role.value,
                "name": role.value.title(),
                "permissions": [p.value for p in ROLE_PERMISSIONS[role]],
            }
            for role in UserRole
        ]


class SCIMService:
    """SCIMユーザープロビジョニングサービス"""

    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}
        self._groups: Dict[str, Dict[str, Any]] = {}

    async def create_user(
        self,
        email: str,
        name: str,
        external_id: Optional[str] = None,
        groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """ユーザーを作成 (SCIM)"""
        user_id = str(uuid.uuid4())

        user = {
            "id": user_id,
            "externalId": external_id,
            "userName": email,
            "name": {
                "formatted": name,
                "givenName": name.split()[0] if name else "",
                "familyName": name.split()[-1] if name and len(name.split()) > 1 else "",
            },
            "emails": [{"value": email, "primary": True, "type": "work"}],
            "active": True,
            "groups": groups or [],
            "meta": {
                "resourceType": "User",
                "created": datetime.utcnow().isoformat(),
                "lastModified": datetime.utcnow().isoformat(),
            },
        }

        self._users[user_id] = user
        return user

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """ユーザーを取得"""
        return self._users.get(user_id)

    async def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """ユーザーを更新"""
        if user_id not in self._users:
            return None

        user = self._users[user_id]

        if "userName" in updates:
            user["userName"] = updates["userName"]
        if "name" in updates:
            user["name"] = updates["name"]
        if "emails" in updates:
            user["emails"] = updates["emails"]
        if "active" in updates:
            user["active"] = updates["active"]
        if "groups" in updates:
            user["groups"] = updates["groups"]

        user["meta"]["lastModified"] = datetime.utcnow().isoformat()
        return user

    async def delete_user(self, user_id: str) -> bool:
        """ユーザーを削除"""
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False

    async def list_users(
        self,
        filter_query: Optional[str] = None,
        start_index: int = 1,
        count: int = 100,
    ) -> Dict[str, Any]:
        """ユーザー一覧を取得"""
        users = list(self._users.values())

        # フィルタ適用（簡易実装）
        if filter_query:
            # email フィルタ
            if 'userName eq' in filter_query:
                email = filter_query.split('"')[1]
                users = [u for u in users if u["userName"] == email]

        total = len(users)
        users = users[start_index - 1:start_index - 1 + count]

        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": len(users),
            "Resources": users,
        }

    async def create_group(
        self,
        display_name: str,
        members: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """グループを作成"""
        group_id = str(uuid.uuid4())

        group = {
            "id": group_id,
            "displayName": display_name,
            "members": [{"value": m} for m in (members or [])],
            "meta": {
                "resourceType": "Group",
                "created": datetime.utcnow().isoformat(),
                "lastModified": datetime.utcnow().isoformat(),
            },
        }

        self._groups[group_id] = group
        return group

    async def update_group_members(
        self,
        group_id: str,
        members: List[str],
    ) -> Optional[Dict[str, Any]]:
        """グループメンバーを更新"""
        if group_id not in self._groups:
            return None

        group = self._groups[group_id]
        group["members"] = [{"value": m} for m in members]
        group["meta"]["lastModified"] = datetime.utcnow().isoformat()
        return group

    async def list_groups(
        self,
        start_index: int = 1,
        count: int = 100,
    ) -> Dict[str, Any]:
        """グループ一覧を取得"""
        groups = list(self._groups.values())
        total = len(groups)
        groups = groups[start_index - 1:start_index - 1 + count]

        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": len(groups),
            "Resources": groups,
        }
