"""API管理エンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.rate_limit_service import (
    RateLimitService,
    APIBillingService,
    WebhookService,
    RateLimitTier,
    RATE_LIMIT_CONFIGS,
)

router = APIRouter(prefix="/api-management", tags=["api-management"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tier() -> RateLimitTier:
    return RateLimitTier.PROFESSIONAL


# === レート制限 ===

class RateLimitStatusResponse(BaseModel):
    tier: str
    limits: dict
    current_usage: dict
    remaining: dict


@router.get("/rate-limit/status", response_model=RateLimitStatusResponse)
async def get_rate_limit_status(
    user_id: uuid.UUID = Depends(get_current_user_id),
    tier: RateLimitTier = Depends(get_current_tier),
):
    """レート制限ステータスを取得"""
    service = RateLimitService()
    config = RATE_LIMIT_CONFIGS[tier]
    usage = await service.get_usage_stats(user_id)

    return RateLimitStatusResponse(
        tier=tier.value,
        limits={
            "requests_per_minute": config.requests_per_minute,
            "requests_per_hour": config.requests_per_hour,
            "requests_per_day": config.requests_per_day,
            "max_file_size_mb": config.max_file_size_mb,
            "max_duration_minutes": config.max_duration_minutes,
            "concurrent_jobs": config.concurrent_jobs,
        },
        current_usage=usage,
        remaining={
            "requests_this_minute": config.requests_per_minute - usage["requests_this_minute"],
            "requests_this_hour": config.requests_per_hour - usage["requests_this_hour"],
            "requests_today": config.requests_per_day - usage["requests_today"],
        },
    )


@router.get("/rate-limit/tiers")
async def get_available_tiers():
    """利用可能なティア一覧を取得"""
    return {
        tier.value: {
            "requests_per_minute": config.requests_per_minute,
            "requests_per_hour": config.requests_per_hour,
            "requests_per_day": config.requests_per_day,
            "max_file_size_mb": config.max_file_size_mb,
            "max_duration_minutes": config.max_duration_minutes,
            "concurrent_jobs": config.concurrent_jobs,
        }
        for tier, config in RATE_LIMIT_CONFIGS.items()
    }


# === 使用量・課金 ===

class UsageResponse(BaseModel):
    period: str
    request_count: int
    transcription_minutes: float
    storage_bytes: int


class BillResponse(BaseModel):
    period: str
    line_items: List[dict]
    subtotal: float
    tax: float
    total: float
    currency: str


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    year: int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """使用量を取得"""
    now = datetime.utcnow()
    if not year:
        year = now.year
    if not month:
        month = now.month

    service = APIBillingService(db)
    usage = await service.get_monthly_usage(user_id, year, month)

    return UsageResponse(
        period=usage.period,
        request_count=usage.request_count,
        transcription_minutes=usage.transcription_minutes,
        storage_bytes=usage.storage_bytes,
    )


@router.get("/usage/history")
async def get_usage_history(
    months: int = Query(6, le=12),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """使用量履歴を取得"""
    service = APIBillingService(db)
    history = await service.get_usage_history(user_id, months)

    return {"history": history}


@router.get("/billing", response_model=BillResponse)
async def get_billing(
    year: int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """請求情報を取得"""
    now = datetime.utcnow()
    if not year:
        year = now.year
    if not month:
        month = now.month

    service = APIBillingService(db)
    bill = await service.calculate_monthly_bill(user_id, year, month)

    return BillResponse(
        period=bill["period"],
        line_items=bill["line_items"],
        subtotal=bill["subtotal"],
        tax=bill["tax"],
        total=bill["total"],
        currency=bill["currency"],
    )


# === Webhook ===

class WebhookCreateRequest(BaseModel):
    url: HttpUrl
    events: List[str]


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    is_active: bool
    created_at: str


@router.post("/webhooks", response_model=WebhookResponse)
async def create_webhook(
    request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを登録"""
    valid_events = [
        "transcription.created",
        "transcription.completed",
        "transcription.failed",
        "analysis.completed",
        "export.completed",
    ]

    for event in request.events:
        if event not in valid_events and event != "*":
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event: {event}. Valid events: {valid_events}",
            )

    service = WebhookService(db)
    webhook_id = await service.register_webhook(
        user_id=user_id,
        url=str(request.url),
        events=request.events,
    )

    return WebhookResponse(
        id=webhook_id,
        url=str(request.url),
        events=request.events,
        is_active=True,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get("/webhooks", response_model=List[WebhookResponse])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhook一覧を取得"""
    service = WebhookService(db)
    webhooks = await service.get_webhooks(user_id)

    return [
        WebhookResponse(
            id=w["id"],
            url=w["url"],
            events=w["events"],
            is_active=w["is_active"],
            created_at=w["created_at"].isoformat() if isinstance(w["created_at"], datetime) else w["created_at"],
        )
        for w in webhooks
    ]


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを削除"""
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM webhooks WHERE id = :id AND user_id = :user_id"),
        {"id": webhook_id, "user_id": str(user_id)},
    )
    await db.commit()

    return {"status": "deleted", "webhook_id": webhook_id}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookをテスト"""
    service = WebhookService(db)

    results = await service.send_webhook(
        user_id=user_id,
        event="test",
        payload={
            "event": "test",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": "This is a test webhook"},
        },
    )

    return {"status": "sent", "results": results}


# === APIキー管理 ===

class APIKeyCreateRequest(BaseModel):
    name: str
    scopes: List[str] = ["read"]


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: List[str]
    created_at: str
    last_used_at: Optional[str] = None


@router.post("/api-keys")
async def create_api_key(
    request: APIKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """APIキーを作成"""
    import secrets
    from sqlalchemy import text

    key_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    key_prefix = api_key[:8]

    # ハッシュ化して保存
    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    await db.execute(
        text("""
            INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, created_at)
            VALUES (:id, :user_id, :name, :key_hash, :key_prefix, :scopes, :created_at)
        """),
        {
            "id": key_id,
            "user_id": str(user_id),
            "name": request.name,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "scopes": ",".join(request.scopes),
            "created_at": datetime.utcnow(),
        },
    )
    await db.commit()

    return {
        "id": key_id,
        "name": request.name,
        "key": api_key,  # 作成時のみ完全なキーを返す
        "key_prefix": key_prefix,
        "scopes": request.scopes,
        "warning": "このAPIキーは一度しか表示されません。安全に保管してください。",
    }


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """APIキー一覧を取得"""
    from sqlalchemy import text

    result = await db.execute(
        text("""
            SELECT id, name, key_prefix, scopes, created_at, last_used_at
            FROM api_keys
            WHERE user_id = :user_id
        """),
        {"user_id": str(user_id)},
    )

    return [
        APIKeyResponse(
            id=row[0],
            name=row[1],
            key_prefix=row[2],
            scopes=row[3].split(",") if row[3] else [],
            created_at=row[4].isoformat() if isinstance(row[4], datetime) else row[4],
            last_used_at=row[5].isoformat() if row[5] else None,
        )
        for row in result.fetchall()
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """APIキーを無効化"""
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM api_keys WHERE id = :id AND user_id = :user_id"),
        {"id": key_id, "user_id": str(user_id)},
    )
    await db.commit()

    return {"status": "revoked", "key_id": key_id}
