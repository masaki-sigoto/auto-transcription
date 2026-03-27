"""マルチテナント・ホワイトラベルAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.multitenant_service import (
    tenant_manager,
    usage_tracker,
    whitelabel_service,
    TenantStatus,
    SubscriptionPlan,
    TenantBranding,
    TenantLimits,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tenant_id(request: Request) -> Optional[str]:
    """リクエストからテナントIDを取得"""
    # ヘッダー、サブドメイン、またはユーザーから取得
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    # ホストからサブドメインを抽出
    host = request.headers.get("host", "")
    if "." in host:
        subdomain = host.split(".")[0]
        tenant = await tenant_manager.get_tenant_by_slug(subdomain)
        if tenant:
            return tenant.id

    return None


# === テナント管理 ===

class CreateTenantRequest(BaseModel):
    name: str
    slug: str
    plan: SubscriptionPlan = SubscriptionPlan.FREE


@router.post("")
async def create_tenant(
    request: CreateTenantRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テナントを作成"""
    # スラグの重複チェック
    existing = await tenant_manager.get_tenant_by_slug(request.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Slug already in use")

    tenant = await tenant_manager.create_tenant(
        name=request.name,
        slug=request.slug,
        owner_id=str(user_id),
        plan=request.plan,
    )

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status.value,
        "plan": tenant.plan.value,
        "created_at": tenant.created_at.isoformat(),
    }


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テナント情報を取得"""
    tenant = await tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status.value,
        "plan": tenant.plan.value,
        "created_at": tenant.created_at.isoformat(),
        "updated_at": tenant.updated_at.isoformat(),
        "limits": {
            "max_users": tenant.limits.max_users,
            "max_transcriptions_per_month": tenant.limits.max_transcriptions_per_month,
            "max_audio_hours_per_month": tenant.limits.max_audio_hours_per_month,
            "max_storage_gb": tenant.limits.max_storage_gb,
            "features": tenant.limits.features,
        },
    }


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[TenantStatus] = None


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    request: UpdateTenantRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テナントを更新"""
    tenant = await tenant_manager.update_tenant(
        tenant_id=tenant_id,
        name=request.name,
        status=request.status,
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "id": tenant.id,
        "name": tenant.name,
        "status": tenant.status.value,
        "updated_at": tenant.updated_at.isoformat(),
    }


# === プラン管理 ===

class UpdatePlanRequest(BaseModel):
    plan: SubscriptionPlan
    custom_limits: Optional[dict] = None


@router.post("/{tenant_id}/plan")
async def update_plan(
    tenant_id: str,
    request: UpdatePlanRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """プランを更新"""
    custom_limits = None
    if request.custom_limits:
        custom_limits = TenantLimits(**request.custom_limits)

    tenant = await tenant_manager.update_plan(
        tenant_id=tenant_id,
        plan=request.plan,
        custom_limits=custom_limits,
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "id": tenant.id,
        "plan": tenant.plan.value,
        "limits": {
            "max_users": tenant.limits.max_users,
            "max_transcriptions_per_month": tenant.limits.max_transcriptions_per_month,
            "max_audio_hours_per_month": tenant.limits.max_audio_hours_per_month,
            "features": tenant.limits.features,
        },
    }


@router.get("/plans/available")
async def list_available_plans():
    """利用可能なプラン一覧"""
    return {
        "plans": [
            {
                "id": SubscriptionPlan.FREE.value,
                "name": "Free",
                "price_monthly": 0,
                "description": "個人利用向け",
                "features": ["基本文字起こし", "月10回まで"],
            },
            {
                "id": SubscriptionPlan.STARTER.value,
                "name": "Starter",
                "price_monthly": 1980,
                "description": "スモールチーム向け",
                "features": ["月100回まで", "話者識別", "エクスポート"],
            },
            {
                "id": SubscriptionPlan.PROFESSIONAL.value,
                "name": "Professional",
                "price_monthly": 4980,
                "description": "成長中のチーム向け",
                "features": ["月500回まで", "API連携", "分析", "カスタム語彙"],
            },
            {
                "id": SubscriptionPlan.ENTERPRISE.value,
                "name": "Enterprise",
                "price_monthly": None,
                "description": "大企業向け",
                "features": ["無制限", "SSO", "監査ログ", "優先サポート", "カスタムモデル"],
            },
        ]
    }


# === ユーザー管理 ===

class AddUserRequest(BaseModel):
    user_id: str


@router.post("/{tenant_id}/users")
async def add_user_to_tenant(
    tenant_id: str,
    request: AddUserRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テナントにユーザーを追加"""
    success = await tenant_manager.add_user_to_tenant(tenant_id, request.user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot add user. Limit may be exceeded.")

    return {"status": "added", "user_id": request.user_id}


@router.delete("/{tenant_id}/users/{user_id}")
async def remove_user_from_tenant(
    tenant_id: str,
    target_user_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テナントからユーザーを削除"""
    success = await tenant_manager.remove_user_from_tenant(tenant_id, target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found in tenant")

    return {"status": "removed", "user_id": target_user_id}


# === 使用量 ===

@router.get("/{tenant_id}/usage")
async def get_usage(
    tenant_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """使用量を取得"""
    summary = await usage_tracker.get_usage_summary(tenant_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return summary


@router.get("/{tenant_id}/usage/check/{limit_type}")
async def check_limit(
    tenant_id: str,
    limit_type: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """制限をチェック"""
    result = await usage_tracker.check_limit(tenant_id, limit_type)
    return result


# === ブランディング ===

@router.get("/{tenant_id}/branding")
async def get_branding(
    tenant_id: str,
):
    """ブランディング設定を取得"""
    branding = await whitelabel_service.get_branding(tenant_id)
    if not branding:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return branding


class UpdateBrandingRequest(BaseModel):
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    custom_css: Optional[str] = None


@router.patch("/{tenant_id}/branding")
async def update_branding(
    tenant_id: str,
    request: UpdateBrandingRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ブランディングを更新"""
    branding = await whitelabel_service.update_branding(
        tenant_id=tenant_id,
        logo_url=request.logo_url,
        favicon_url=request.favicon_url,
        primary_color=request.primary_color,
        secondary_color=request.secondary_color,
        accent_color=request.accent_color,
        font_family=request.font_family,
        custom_css=request.custom_css,
    )

    if not branding:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return branding


# === カスタムドメイン ===

class SetupDomainRequest(BaseModel):
    domain: str


@router.post("/{tenant_id}/domain")
async def setup_custom_domain(
    tenant_id: str,
    request: SetupDomainRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """カスタムドメインを設定"""
    result = await whitelabel_service.setup_custom_domain(tenant_id, request.domain)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# === 埋め込み ===

@router.get("/{tenant_id}/embed")
async def get_embed_code(
    tenant_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """埋め込みコードを取得"""
    embed = await whitelabel_service.generate_embed_code(tenant_id)
    if not embed:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return embed


# === テナント解決 ===

@router.get("/resolve/by-domain/{domain}")
async def resolve_by_domain(domain: str):
    """ドメインからテナントを解決"""
    tenant = await tenant_manager.get_tenant_by_domain(domain)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
    }


@router.get("/resolve/by-slug/{slug}")
async def resolve_by_slug(slug: str):
    """スラグからテナントを解決"""
    tenant = await tenant_manager.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
    }
