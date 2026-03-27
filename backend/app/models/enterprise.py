"""エンタープライズ機能モデル"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, JSON, Enum as SQLEnum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.core.database import Base


class SSOProvider(str, enum.Enum):
    """SSOプロバイダー"""
    SAML = "saml"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    AZURE_AD = "azure_ad"
    OKTA = "okta"
    GOOGLE = "google"


class Organization(Base):
    """組織（マルチテナント）"""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)

    # プラン・サブスクリプション
    plan = Column(String(50), default="free")
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    # 制限
    max_users = Column(Integer, default=5)
    max_storage_gb = Column(Integer, default=10)
    max_transcription_hours = Column(Integer, default=10)

    # 設定
    settings = Column(JSON, default=dict)

    # SSO設定
    sso_enabled = Column(Boolean, default=False)
    sso_provider = Column(SQLEnum(SSOProvider), nullable=True)
    sso_config = Column(JSON, nullable=True)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    members = relationship("OrganizationMember", back_populates="organization")
    audit_logs = relationship("EnterpriseAuditLog", back_populates="organization")


class OrganizationRole(str, enum.Enum):
    """組織内ロール"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
    BILLING = "billing"


class OrganizationMember(Base):
    """組織メンバー"""
    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(SQLEnum(OrganizationRole), default=OrganizationRole.MEMBER)

    # 招待情報
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # ステータス
    is_active = Column(Boolean, default=True)

    # リレーション
    organization = relationship("Organization", back_populates="members")


class SSOConfiguration(Base):
    """SSO設定"""
    __tablename__ = "sso_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    provider = Column(SQLEnum(SSOProvider), nullable=False)

    # SAML設定
    entity_id = Column(String(500), nullable=True)
    sso_url = Column(String(500), nullable=True)
    slo_url = Column(String(500), nullable=True)
    certificate = Column(Text, nullable=True)

    # OAuth2/OIDC設定
    client_id = Column(String(255), nullable=True)
    client_secret = Column(String(500), nullable=True)
    authorization_url = Column(String(500), nullable=True)
    token_url = Column(String(500), nullable=True)
    userinfo_url = Column(String(500), nullable=True)

    # 属性マッピング
    attribute_mapping = Column(JSON, default=dict)

    # ステータス
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EnterpriseAuditLog(Base):
    """エンタープライズ監査ログ"""
    __tablename__ = "enterprise_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # アクション情報
    action = Column(String(100), nullable=False)
    action_category = Column(String(50), nullable=False)  # auth, data, admin, billing
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)

    # 詳細
    details = Column(JSON, default=dict)
    changes = Column(JSON, nullable=True)  # 変更前後の値

    # リクエスト情報
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_id = Column(String(100), nullable=True)

    # コンプライアンス
    is_sensitive = Column(Boolean, default=False)
    retention_days = Column(Integer, default=365)

    # タイムスタンプ
    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    organization = relationship("Organization", back_populates="audit_logs")


class SubscriptionPlan(Base):
    """サブスクリプションプラン"""
    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    # 価格（月額）
    price_monthly = Column(Numeric(10, 2), nullable=False)
    price_yearly = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="JPY")

    # Stripe
    stripe_price_id_monthly = Column(String(255), nullable=True)
    stripe_price_id_yearly = Column(String(255), nullable=True)

    # 制限
    max_users = Column(Integer, nullable=True)
    max_storage_gb = Column(Integer, nullable=True)
    max_transcription_hours_monthly = Column(Integer, nullable=True)
    max_api_calls_monthly = Column(Integer, nullable=True)

    # 機能フラグ
    features = Column(JSON, default=dict)

    # ステータス
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Subscription(Base):
    """サブスクリプション"""
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)

    # Stripe情報
    stripe_subscription_id = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)

    # 期間
    billing_cycle = Column(String(20), default="monthly")  # monthly, yearly
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)

    # ステータス
    status = Column(String(50), default="active")  # active, past_due, canceled, trialing
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UsageRecord(Base):
    """使用量レコード"""
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    # 使用量タイプ
    usage_type = Column(String(50), nullable=False)  # transcription, storage, api_calls

    # 数量
    quantity = Column(Numeric(20, 4), nullable=False)
    unit = Column(String(20), nullable=False)  # seconds, bytes, calls

    # 課金
    unit_price = Column(Numeric(10, 4), nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=True)

    # 期間
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Stripe
    stripe_usage_record_id = Column(String(255), nullable=True)
    reported_to_stripe = Column(Boolean, default=False)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)


class Invoice(Base):
    """請求書"""
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    # Stripe
    stripe_invoice_id = Column(String(255), nullable=True)

    # 金額
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="JPY")

    # ステータス
    status = Column(String(50), default="draft")  # draft, open, paid, void, uncollectible

    # 期間
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    # PDF
    invoice_pdf_url = Column(String(500), nullable=True)

    # メタデータ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
