import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class AuditAction(str, enum.Enum):
    # 認証関連
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGED = "password_changed"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"

    # 文字起こし関連
    TRANSCRIPTION_CREATED = "transcription_created"
    TRANSCRIPTION_UPDATED = "transcription_updated"
    TRANSCRIPTION_DELETED = "transcription_deleted"
    TRANSCRIPTION_EXPORTED = "transcription_exported"
    TRANSCRIPTION_SHARED = "transcription_shared"
    TRANSCRIPTION_UNSHARED = "transcription_unshared"

    # チーム関連
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_DELETED = "team_deleted"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    MEMBER_ROLE_CHANGED = "member_role_changed"

    # 連携関連
    INTEGRATION_CONNECTED = "integration_connected"
    INTEGRATION_DISCONNECTED = "integration_disconnected"

    # 管理者アクション
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_SUSPENDED = "user_suspended"
    USER_ACTIVATED = "user_activated"
    SETTINGS_CHANGED = "settings_changed"

    # API関連
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"


class AuditLog(Base):
    """監査ログモデル"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=True)  # e.g., "transcription", "team", "user"
    resource_id = Column(UUID(as_uuid=True), nullable=True)

    # リクエスト情報
    ip_address = Column(String(45), nullable=True)  # IPv6対応
    user_agent = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)

    # 詳細情報
    details = Column(JSON, default=dict)  # 変更内容などの詳細
    old_value = Column(JSON, nullable=True)  # 変更前の値
    new_value = Column(JSON, nullable=True)  # 変更後の値

    # 結果
    status = Column(String(20), default="success")  # success, failure
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    user = relationship("User")


class SSOProvider(Base):
    """SSO プロバイダー設定モデル"""
    __tablename__ = "sso_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(50), nullable=False)  # saml, oidc
    is_active = Column(String(10), default="true")

    # SAML設定
    entity_id = Column(String(500), nullable=True)
    sso_url = Column(String(500), nullable=True)
    slo_url = Column(String(500), nullable=True)
    certificate = Column(Text, nullable=True)

    # OIDC設定
    client_id = Column(String(255), nullable=True)
    client_secret = Column(String(500), nullable=True)
    authorization_url = Column(String(500), nullable=True)
    token_url = Column(String(500), nullable=True)
    userinfo_url = Column(String(500), nullable=True)
    scopes = Column(String(500), default="openid profile email")

    # ドメイン制限
    allowed_domains = Column(JSON, default=list)  # 許可するメールドメイン

    # 属性マッピング
    attribute_mapping = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class APIKey(Base):
    """API キーモデル"""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False)  # ハッシュ化したキー
    key_prefix = Column(String(10), nullable=False)  # 表示用のプレフィックス

    # スコープ・権限
    scopes = Column(JSON, default=list)  # 許可されるAPIスコープ

    # 有効期限
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    # リレーション
    user = relationship("User")


class SecurityPolicy(Base):
    """セキュリティポリシーモデル"""
    __tablename__ = "security_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)

    # パスワードポリシー
    password_min_length = Column(String(10), default="8")
    password_require_uppercase = Column(String(10), default="true")
    password_require_lowercase = Column(String(10), default="true")
    password_require_numbers = Column(String(10), default="true")
    password_require_special = Column(String(10), default="false")
    password_max_age_days = Column(String(10), default="90")

    # セッションポリシー
    session_timeout_minutes = Column(String(10), default="60")
    max_concurrent_sessions = Column(String(10), default="5")
    require_mfa = Column(String(10), default="false")

    # IPホワイトリスト
    ip_whitelist = Column(JSON, default=list)
    ip_whitelist_enabled = Column(String(10), default="false")

    # データ保持ポリシー
    data_retention_days = Column(String(10), default="365")
    audit_log_retention_days = Column(String(10), default="730")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
