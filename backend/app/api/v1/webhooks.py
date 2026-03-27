import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl

from app.core.database import get_db
from app.services.webhook_service import WebhookService, WEBHOOK_EVENTS

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# 仮のユーザーID取得（認証実装後に置き換え）
async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class WebhookCreate(BaseModel):
    name: str
    url: HttpUrl
    events: list[str]
    secret: str | None = None


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: HttpUrl | None = None
    events: list[str] | None = None
    secret: str | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    events: list[str]
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WebhookLogResponse(BaseModel):
    id: uuid.UUID
    event: str
    payload: dict
    status_code: int | None
    error_message: str | None
    created_at: str

    class Config:
        from_attributes = True


@router.get("/events")
async def list_webhook_events():
    """利用可能なWebhookイベント一覧"""
    return WEBHOOK_EVENTS


@router.post("", response_model=WebhookResponse)
async def create_webhook(
    data: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを作成"""
    # イベントの検証
    for event in data.events:
        if event not in WEBHOOK_EVENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event: {event}. Valid events: {list(WEBHOOK_EVENTS.keys())}",
            )

    service = WebhookService(db)
    webhook = await service.create(
        user_id=user_id,
        name=data.name,
        url=str(data.url),
        events=data.events,
        secret=data.secret,
    )

    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at.isoformat(),
        updated_at=webhook.updated_at.isoformat(),
    )


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhook一覧を取得"""
    service = WebhookService(db)
    webhooks = await service.list_by_user(user_id)

    return [
        WebhookResponse(
            id=w.id,
            name=w.name,
            url=w.url,
            events=w.events,
            is_active=w.is_active,
            created_at=w.created_at.isoformat(),
            updated_at=w.updated_at.isoformat(),
        )
        for w in webhooks
    ]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを取得"""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id, user_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at.isoformat(),
        updated_at=webhook.updated_at.isoformat(),
    )


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: uuid.UUID,
    data: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを更新"""
    # イベントの検証
    if data.events:
        for event in data.events:
            if event not in WEBHOOK_EVENTS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event: {event}",
                )

    service = WebhookService(db)
    updates = data.model_dump(exclude_unset=True)
    if "url" in updates and updates["url"]:
        updates["url"] = str(updates["url"])

    webhook = await service.update(webhook_id, user_id, **updates)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at.isoformat(),
        updated_at=webhook.updated_at.isoformat(),
    )


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookを削除"""
    service = WebhookService(db)
    deleted = await service.delete(webhook_id, user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.get("/{webhook_id}/logs", response_model=list[WebhookLogResponse])
async def get_webhook_logs(
    webhook_id: uuid.UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhook送信ログを取得"""
    service = WebhookService(db)

    # Webhookの存在確認
    webhook = await service.get_by_id(webhook_id, user_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    logs = await service.get_logs(webhook_id, limit)

    return [
        WebhookLogResponse(
            id=log.id,
            event=log.event,
            payload=log.payload,
            status_code=log.status_code,
            error_message=log.error_message,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Webhookをテスト送信"""
    from app.services.webhook_service import WebhookDispatcher

    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id, user_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_data = {
        "transcription_id": "test-id",
        "title": "テスト文字起こし",
        "status": "completed",
        "message": "これはテスト送信です",
    }

    log = await WebhookDispatcher.dispatch(
        webhook, "test", test_data, db
    )

    return {
        "success": log.status_code is not None and 200 <= log.status_code < 300,
        "status_code": log.status_code,
        "error_message": log.error_message,
    }
