"""エンタープライズAPIエンドポイント"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.config import get_settings
from app.models.enterprise import (
    Organization,
    OrganizationMember,
    OrganizationRole,
    SSOConfiguration,
    SSOProvider,
    EnterpriseAuditLog,
    SubscriptionPlan,
)
from app.services.sso_service import SSOService
from app.services.billing_service import BillingService, CreateSubscriptionRequest

router = APIRouter(tags=["enterprise"])


# === 組織管理 ===

class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    domain: Optional[str] = None


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    settings: Optional[dict] = None


@router.post("/organizations", status_code=201)
async def create_organization(
    request: CreateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
):
    """組織を作成"""
    org = Organization(
        name=request.name,
        slug=request.slug,
        domain=request.domain,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "domain": org.domain,
        "plan": org.plan,
        "created_at": org.created_at.isoformat(),
    }


@router.get("/organizations/{org_id}")
async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """組織を取得"""
    from sqlalchemy import select

    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "domain": org.domain,
        "plan": org.plan,
        "sso_enabled": org.sso_enabled,
        "max_users": org.max_users,
        "max_storage_gb": org.max_storage_gb,
        "max_transcription_hours": org.max_transcription_hours,
        "created_at": org.created_at.isoformat(),
    }


@router.patch("/organizations/{org_id}")
async def update_organization(
    org_id: UUID,
    request: UpdateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
):
    """組織を更新"""
    from sqlalchemy import select

    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if request.name:
        org.name = request.name
    if request.domain:
        org.domain = request.domain
    if request.settings:
        org.settings = {**org.settings, **request.settings}

    await db.commit()
    await db.refresh(org)

    return {"status": "updated"}


# === メンバー管理 ===

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: OrganizationRole = OrganizationRole.MEMBER


@router.get("/organizations/{org_id}/members")
async def list_members(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """メンバー一覧を取得"""
    from sqlalchemy import select

    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == org_id)
        .where(OrganizationMember.is_active == True)
    )
    members = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "role": m.role.value,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m in members
    ]


@router.post("/organizations/{org_id}/members/invite")
async def invite_member(
    org_id: UUID,
    request: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """メンバーを招待"""
    # 招待ロジック（メール送信など）を実装
    return {
        "status": "invited",
        "email": request.email,
        "role": request.role.value,
    }


@router.delete("/organizations/{org_id}/members/{member_id}")
async def remove_member(
    org_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """メンバーを削除"""
    from sqlalchemy import select

    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.id == member_id)
        .where(OrganizationMember.organization_id == org_id)
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.is_active = False
    await db.commit()

    return {"status": "removed"}


# === SSO設定 ===

class ConfigureSSORequest(BaseModel):
    provider: SSOProvider
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    certificate: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    attribute_mapping: Optional[dict] = None


@router.get("/organizations/{org_id}/sso")
async def get_sso_config(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """SSO設定を取得"""
    service = SSOService(db)
    config = await service.get_sso_config(org_id)

    if not config:
        return {"enabled": False}

    return {
        "enabled": True,
        "provider": config.provider.value,
        "is_verified": config.is_verified,
    }


@router.post("/organizations/{org_id}/sso")
async def configure_sso(
    org_id: UUID,
    request: ConfigureSSORequest,
    db: AsyncSession = Depends(get_db),
):
    """SSOを設定"""
    from sqlalchemy import select

    # 既存設定を無効化
    result = await db.execute(
        select(SSOConfiguration)
        .where(SSOConfiguration.organization_id == org_id)
        .where(SSOConfiguration.is_active == True)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_active = False

    # 新しい設定を作成
    config = SSOConfiguration(
        organization_id=org_id,
        provider=request.provider,
        entity_id=request.entity_id,
        sso_url=request.sso_url,
        certificate=request.certificate,
        client_id=request.client_id,
        client_secret=request.client_secret,
        attribute_mapping=request.attribute_mapping or {},
    )
    db.add(config)

    # 組織のSSO設定を有効化
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one()
    org.sso_enabled = True
    org.sso_provider = request.provider

    await db.commit()

    return {"status": "configured", "provider": request.provider.value}


@router.get("/sso/{org_slug}/login")
async def sso_login(
    org_slug: str,
    redirect_uri: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """SSO認証を開始"""
    service = SSOService(db)

    try:
        result = await service.initiate_sso_login(org_slug, redirect_uri)
        return RedirectResponse(url=result["url"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sso/callback")
async def sso_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """SSOコールバック"""
    form = await request.form()
    params = dict(form)

    # クエリパラメータも確認
    query_params = dict(request.query_params)
    params.update(query_params)

    org_slug = params.get("state", "").split(":")[0] if "state" in params else None

    if not org_slug:
        raise HTTPException(status_code=400, detail="Invalid callback")

    service = SSOService(db)

    try:
        user = await service.handle_sso_callback(
            org_slug,
            code=params.get("code"),
            saml_response=params.get("SAMLResponse"),
            state=params.get("state"),
        )

        # JWTトークンを生成してリダイレクト
        # 実際の実装ではトークン生成ロジックを追加
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback?user_id={user.id}")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === 監査ログ ===

@router.get("/organizations/{org_id}/audit-logs")
async def list_audit_logs(
    org_id: UUID,
    action_category: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """監査ログを取得"""
    from sqlalchemy import select, and_

    query = select(EnterpriseAuditLog).where(
        EnterpriseAuditLog.organization_id == org_id
    )

    if action_category:
        query = query.where(EnterpriseAuditLog.action_category == action_category)
    if start_date:
        query = query.where(EnterpriseAuditLog.created_at >= start_date)
    if end_date:
        query = query.where(EnterpriseAuditLog.created_at <= end_date)

    query = query.order_by(EnterpriseAuditLog.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "action_category": log.action_category,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "user_id": str(log.user_id) if log.user_id else None,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/organizations/{org_id}/audit-logs/export")
async def export_audit_logs(
    org_id: UUID,
    format: str = Query("csv", regex="^(csv|json)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """監査ログをエクスポート"""
    from fastapi.responses import StreamingResponse
    import csv
    import io
    import json

    from sqlalchemy import select

    query = select(EnterpriseAuditLog).where(
        EnterpriseAuditLog.organization_id == org_id
    )

    if start_date:
        query = query.where(EnterpriseAuditLog.created_at >= start_date)
    if end_date:
        query = query.where(EnterpriseAuditLog.created_at <= end_date)

    result = await db.execute(query.order_by(EnterpriseAuditLog.created_at))
    logs = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "action", "category", "resource_type", "resource_id", "user_id", "ip_address"])

        for log in logs:
            writer.writerow([
                log.created_at.isoformat(),
                log.action,
                log.action_category,
                log.resource_type,
                log.resource_id,
                str(log.user_id) if log.user_id else "",
                log.ip_address or "",
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )
    else:
        data = [
            {
                "timestamp": log.created_at.isoformat(),
                "action": log.action,
                "action_category": log.action_category,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "user_id": str(log.user_id) if log.user_id else None,
                "ip_address": log.ip_address,
                "details": log.details,
            }
            for log in logs
        ]

        return StreamingResponse(
            iter([json.dumps(data, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit_logs.json"},
        )


# === 請求・サブスクリプション ===

@router.get("/billing/plans")
async def list_plans(
    db: AsyncSession = Depends(get_db),
):
    """プラン一覧を取得"""
    service = BillingService(db)
    plans = await service.get_plans()

    return [
        {
            "id": str(plan.id),
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price_monthly": float(plan.price_monthly),
            "price_yearly": float(plan.price_yearly) if plan.price_yearly else None,
            "currency": plan.currency,
            "max_users": plan.max_users,
            "max_storage_gb": plan.max_storage_gb,
            "max_transcription_hours": plan.max_transcription_hours_monthly,
            "features": plan.features,
        }
        for plan in plans
    ]


@router.get("/organizations/{org_id}/subscription")
async def get_subscription(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """サブスクリプションを取得"""
    service = BillingService(db)
    subscription = await service.get_subscription(org_id)

    if not subscription:
        return {"status": "no_subscription"}

    return {
        "id": str(subscription.id),
        "plan_id": str(subscription.plan_id),
        "status": subscription.status,
        "billing_cycle": subscription.billing_cycle,
        "current_period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "cancel_at_period_end": subscription.cancel_at_period_end,
    }


@router.post("/organizations/{org_id}/subscription")
async def create_subscription(
    org_id: UUID,
    request: CreateSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
):
    """サブスクリプションを作成"""
    service = BillingService(db)

    try:
        subscription = await service.create_subscription(org_id, request)
        return {
            "id": str(subscription.id),
            "status": subscription.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/organizations/{org_id}/subscription")
async def cancel_subscription(
    org_id: UUID,
    at_period_end: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """サブスクリプションをキャンセル"""
    service = BillingService(db)

    try:
        await service.cancel_subscription(org_id, at_period_end)
        return {"status": "canceled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/organizations/{org_id}/usage")
async def get_usage(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """使用量を取得"""
    service = BillingService(db)
    usage = await service.get_usage_summary(org_id)
    return usage


@router.get("/organizations/{org_id}/invoices")
async def list_invoices(
    org_id: UUID,
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
):
    """請求書一覧を取得"""
    service = BillingService(db)
    invoices = await service.get_invoices(org_id, limit)

    return [
        {
            "id": str(inv.id),
            "total": float(inv.total),
            "currency": inv.currency,
            "status": inv.status,
            "period_start": inv.period_start.isoformat() if inv.period_start else None,
            "period_end": inv.period_end.isoformat() if inv.period_end else None,
            "pdf_url": inv.invoice_pdf_url,
            "created_at": inv.created_at.isoformat(),
        }
        for inv in invoices
    ]
