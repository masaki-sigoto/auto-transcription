"""マルチテナント・ホワイトラベルサービス"""

import os
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    CANCELLED = "cancelled"


class SubscriptionPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


@dataclass
class TenantBranding:
    """テナントブランディング設定"""
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#3B82F6"
    secondary_color: str = "#1E40AF"
    accent_color: str = "#10B981"
    font_family: str = "Inter, sans-serif"
    custom_css: Optional[str] = None
    custom_domain: Optional[str] = None
    email_from_name: Optional[str] = None
    email_from_address: Optional[str] = None


@dataclass
class TenantLimits:
    """テナント利用制限"""
    max_users: int = 5
    max_transcriptions_per_month: int = 100
    max_audio_hours_per_month: float = 10.0
    max_storage_gb: float = 5.0
    max_api_calls_per_day: int = 1000
    features: List[str] = field(default_factory=list)


@dataclass
class Tenant:
    """テナント"""
    id: str
    name: str
    slug: str
    status: TenantStatus
    plan: SubscriptionPlan
    branding: TenantBranding
    limits: TenantLimits
    created_at: datetime
    updated_at: datetime
    owner_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantUsage:
    """テナント使用量"""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    users_count: int = 0
    transcriptions_count: int = 0
    audio_hours_used: float = 0.0
    storage_used_gb: float = 0.0
    api_calls_count: int = 0


# プラン別のデフォルト制限
PLAN_LIMITS = {
    SubscriptionPlan.FREE: TenantLimits(
        max_users=2,
        max_transcriptions_per_month=10,
        max_audio_hours_per_month=1.0,
        max_storage_gb=1.0,
        max_api_calls_per_day=100,
        features=["basic_transcription"],
    ),
    SubscriptionPlan.STARTER: TenantLimits(
        max_users=5,
        max_transcriptions_per_month=100,
        max_audio_hours_per_month=10.0,
        max_storage_gb=10.0,
        max_api_calls_per_day=1000,
        features=["basic_transcription", "speaker_diarization", "export"],
    ),
    SubscriptionPlan.PROFESSIONAL: TenantLimits(
        max_users=20,
        max_transcriptions_per_month=500,
        max_audio_hours_per_month=50.0,
        max_storage_gb=50.0,
        max_api_calls_per_day=5000,
        features=[
            "basic_transcription", "speaker_diarization", "export",
            "api_access", "analytics", "custom_vocabulary",
        ],
    ),
    SubscriptionPlan.ENTERPRISE: TenantLimits(
        max_users=999999,
        max_transcriptions_per_month=999999,
        max_audio_hours_per_month=999999.0,
        max_storage_gb=999999.0,
        max_api_calls_per_day=999999,
        features=[
            "basic_transcription", "speaker_diarization", "export",
            "api_access", "analytics", "custom_vocabulary",
            "sso", "audit_logs", "priority_support", "custom_models",
        ],
    ),
}


class TenantManager:
    """テナント管理"""

    def __init__(self):
        self._tenants: Dict[str, Tenant] = {}
        self._usage: Dict[str, TenantUsage] = {}
        self._user_tenant_map: Dict[str, str] = {}

    async def create_tenant(
        self,
        name: str,
        slug: str,
        owner_id: str,
        plan: SubscriptionPlan = SubscriptionPlan.FREE,
        branding: Optional[TenantBranding] = None,
    ) -> Tenant:
        """テナントを作成"""
        tenant_id = str(uuid.uuid4())
        now = datetime.utcnow()

        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            status=TenantStatus.ACTIVE,
            plan=plan,
            branding=branding or TenantBranding(),
            limits=PLAN_LIMITS.get(plan, PLAN_LIMITS[SubscriptionPlan.FREE]),
            created_at=now,
            updated_at=now,
            owner_id=owner_id,
        )

        self._tenants[tenant_id] = tenant
        self._user_tenant_map[owner_id] = tenant_id

        # 使用量を初期化
        self._usage[tenant_id] = TenantUsage(
            tenant_id=tenant_id,
            period_start=now,
            period_end=datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1),
        )

        return tenant

    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """テナントを取得"""
        return self._tenants.get(tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """スラグでテナントを取得"""
        for tenant in self._tenants.values():
            if tenant.slug == slug:
                return tenant
        return None

    async def get_tenant_by_domain(self, domain: str) -> Optional[Tenant]:
        """カスタムドメインでテナントを取得"""
        for tenant in self._tenants.values():
            if tenant.branding.custom_domain == domain:
                return tenant
        return None

    async def get_user_tenant(self, user_id: str) -> Optional[Tenant]:
        """ユーザーのテナントを取得"""
        tenant_id = self._user_tenant_map.get(user_id)
        if tenant_id:
            return self._tenants.get(tenant_id)
        return None

    async def update_tenant(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        status: Optional[TenantStatus] = None,
        branding: Optional[TenantBranding] = None,
    ) -> Optional[Tenant]:
        """テナントを更新"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        if name:
            tenant.name = name
        if status:
            tenant.status = status
        if branding:
            tenant.branding = branding
        tenant.updated_at = datetime.utcnow()

        return tenant

    async def update_plan(
        self,
        tenant_id: str,
        plan: SubscriptionPlan,
        custom_limits: Optional[TenantLimits] = None,
    ) -> Optional[Tenant]:
        """プランを更新"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        tenant.plan = plan
        tenant.limits = custom_limits or PLAN_LIMITS.get(plan, PLAN_LIMITS[SubscriptionPlan.FREE])
        tenant.updated_at = datetime.utcnow()

        return tenant

    async def add_user_to_tenant(self, tenant_id: str, user_id: str) -> bool:
        """ユーザーをテナントに追加"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False

        # 制限チェック
        usage = self._usage.get(tenant_id)
        if usage and usage.users_count >= tenant.limits.max_users:
            return False

        self._user_tenant_map[user_id] = tenant_id
        if usage:
            usage.users_count += 1

        return True

    async def remove_user_from_tenant(self, tenant_id: str, user_id: str) -> bool:
        """ユーザーをテナントから削除"""
        if self._user_tenant_map.get(user_id) == tenant_id:
            del self._user_tenant_map[user_id]
            usage = self._usage.get(tenant_id)
            if usage and usage.users_count > 0:
                usage.users_count -= 1
            return True
        return False


class UsageTracker:
    """使用量トラッカー"""

    def __init__(self, tenant_manager: TenantManager):
        self.tenant_manager = tenant_manager

    async def track_transcription(self, tenant_id: str, audio_duration_hours: float):
        """文字起こし使用量を記録"""
        usage = self.tenant_manager._usage.get(tenant_id)
        if usage:
            usage.transcriptions_count += 1
            usage.audio_hours_used += audio_duration_hours

    async def track_api_call(self, tenant_id: str):
        """API呼び出しを記録"""
        usage = self.tenant_manager._usage.get(tenant_id)
        if usage:
            usage.api_calls_count += 1

    async def track_storage(self, tenant_id: str, size_gb: float):
        """ストレージ使用量を記録"""
        usage = self.tenant_manager._usage.get(tenant_id)
        if usage:
            usage.storage_used_gb += size_gb

    async def check_limit(self, tenant_id: str, limit_type: str) -> Dict[str, Any]:
        """制限をチェック"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        usage = self.tenant_manager._usage.get(tenant_id)

        if not tenant or not usage:
            return {"allowed": False, "reason": "Tenant not found"}

        limits = tenant.limits
        checks = {
            "transcriptions": (usage.transcriptions_count, limits.max_transcriptions_per_month),
            "audio_hours": (usage.audio_hours_used, limits.max_audio_hours_per_month),
            "storage": (usage.storage_used_gb, limits.max_storage_gb),
            "api_calls": (usage.api_calls_count, limits.max_api_calls_per_day),
            "users": (usage.users_count, limits.max_users),
        }

        if limit_type not in checks:
            return {"allowed": True}

        current, max_val = checks[limit_type]
        if current >= max_val:
            return {
                "allowed": False,
                "reason": f"{limit_type} limit exceeded",
                "current": current,
                "limit": max_val,
            }

        return {
            "allowed": True,
            "current": current,
            "limit": max_val,
            "remaining": max_val - current,
        }

    async def get_usage_summary(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """使用量サマリーを取得"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        usage = self.tenant_manager._usage.get(tenant_id)

        if not tenant or not usage:
            return None

        limits = tenant.limits

        return {
            "tenant_id": tenant_id,
            "plan": tenant.plan.value,
            "period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat(),
            },
            "usage": {
                "users": {
                    "current": usage.users_count,
                    "limit": limits.max_users,
                    "percentage": (usage.users_count / limits.max_users) * 100,
                },
                "transcriptions": {
                    "current": usage.transcriptions_count,
                    "limit": limits.max_transcriptions_per_month,
                    "percentage": (usage.transcriptions_count / limits.max_transcriptions_per_month) * 100,
                },
                "audio_hours": {
                    "current": usage.audio_hours_used,
                    "limit": limits.max_audio_hours_per_month,
                    "percentage": (usage.audio_hours_used / limits.max_audio_hours_per_month) * 100,
                },
                "storage_gb": {
                    "current": usage.storage_used_gb,
                    "limit": limits.max_storage_gb,
                    "percentage": (usage.storage_used_gb / limits.max_storage_gb) * 100,
                },
                "api_calls": {
                    "current": usage.api_calls_count,
                    "limit": limits.max_api_calls_per_day,
                    "percentage": (usage.api_calls_count / limits.max_api_calls_per_day) * 100,
                },
            },
        }


class WhiteLabelService:
    """ホワイトラベルサービス"""

    def __init__(self, tenant_manager: TenantManager):
        self.tenant_manager = tenant_manager

    async def get_branding(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """ブランディング設定を取得"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return None

        branding = tenant.branding

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "logo_url": branding.logo_url,
            "favicon_url": branding.favicon_url,
            "colors": {
                "primary": branding.primary_color,
                "secondary": branding.secondary_color,
                "accent": branding.accent_color,
            },
            "font_family": branding.font_family,
            "custom_css": branding.custom_css,
            "custom_domain": branding.custom_domain,
            "email": {
                "from_name": branding.email_from_name or tenant.name,
                "from_address": branding.email_from_address,
            },
        }

    async def update_branding(
        self,
        tenant_id: str,
        logo_url: Optional[str] = None,
        favicon_url: Optional[str] = None,
        primary_color: Optional[str] = None,
        secondary_color: Optional[str] = None,
        accent_color: Optional[str] = None,
        font_family: Optional[str] = None,
        custom_css: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """ブランディングを更新"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return None

        branding = tenant.branding
        if logo_url is not None:
            branding.logo_url = logo_url
        if favicon_url is not None:
            branding.favicon_url = favicon_url
        if primary_color is not None:
            branding.primary_color = primary_color
        if secondary_color is not None:
            branding.secondary_color = secondary_color
        if accent_color is not None:
            branding.accent_color = accent_color
        if font_family is not None:
            branding.font_family = font_family
        if custom_css is not None:
            branding.custom_css = custom_css

        tenant.updated_at = datetime.utcnow()

        return await self.get_branding(tenant_id)

    async def setup_custom_domain(
        self,
        tenant_id: str,
        domain: str,
    ) -> Dict[str, Any]:
        """カスタムドメインを設定"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return {"success": False, "error": "Tenant not found"}

        # ドメインの検証（実際にはDNS検証が必要）
        tenant.branding.custom_domain = domain
        tenant.updated_at = datetime.utcnow()

        return {
            "success": True,
            "domain": domain,
            "dns_records": [
                {
                    "type": "CNAME",
                    "name": domain,
                    "value": "app.transcription-service.com",
                },
                {
                    "type": "TXT",
                    "name": f"_verification.{domain}",
                    "value": f"tenant-verify={tenant_id}",
                },
            ],
            "verification_status": "pending",
        }

    async def generate_embed_code(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """埋め込みコードを生成"""
        tenant = await self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return None

        base_url = tenant.branding.custom_domain or "app.transcription-service.com"

        return {
            "iframe": f'<iframe src="https://{base_url}/embed" width="100%" height="600" frameborder="0"></iframe>',
            "script": f'<script src="https://{base_url}/embed.js" data-tenant="{tenant_id}"></script>',
            "react": f'import {{ TranscriptionWidget }} from "@transcription-service/react"; <TranscriptionWidget tenantId="{tenant_id}" />',
        }


# グローバルインスタンス
tenant_manager = TenantManager()
usage_tracker = UsageTracker(tenant_manager)
whitelabel_service = WhiteLabelService(tenant_manager)
