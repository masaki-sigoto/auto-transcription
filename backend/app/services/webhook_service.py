import uuid
import hmac
import hashlib
import json
from datetime import datetime
from typing import Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.webhook import Webhook, WebhookLog
from app.models.transcription import Transcription


# Webhookイベント定義
WEBHOOK_EVENTS = {
    "transcription.created": "文字起こしジョブが作成された",
    "transcription.processing": "文字起こし処理が開始された",
    "transcription.completed": "文字起こしが完了した",
    "transcription.failed": "文字起こしが失敗した",
}


class WebhookService:
    """Webhookサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: uuid.UUID,
        name: str,
        url: str,
        events: list[str],
        secret: Optional[str] = None,
    ) -> Webhook:
        """Webhookを作成"""
        webhook = Webhook(
            user_id=user_id,
            name=name,
            url=url,
            secret=secret,
            events=events,
            is_active=True,
        )
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def list_by_user(self, user_id: uuid.UUID) -> list[Webhook]:
        """ユーザーのWebhook一覧を取得"""
        query = select(Webhook).where(Webhook.user_id == user_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(
        self, webhook_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Webhook]:
        """Webhookを取得"""
        query = select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.user_id == user_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update(
        self,
        webhook_id: uuid.UUID,
        user_id: uuid.UUID,
        **updates,
    ) -> Optional[Webhook]:
        """Webhookを更新"""
        webhook = await self.get_by_id(webhook_id, user_id)
        if not webhook:
            return None

        for key, value in updates.items():
            if hasattr(webhook, key) and value is not None:
                setattr(webhook, key, value)

        webhook.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def delete(self, webhook_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Webhookを削除"""
        webhook = await self.get_by_id(webhook_id, user_id)
        if not webhook:
            return False
        await self.db.delete(webhook)
        return True

    async def get_logs(
        self, webhook_id: uuid.UUID, limit: int = 50
    ) -> list[WebhookLog]:
        """Webhook送信ログを取得"""
        query = (
            select(WebhookLog)
            .where(WebhookLog.webhook_id == webhook_id)
            .order_by(WebhookLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


class WebhookDispatcher:
    """Webhook送信"""

    @staticmethod
    def generate_signature(payload: str, secret: str) -> str:
        """HMAC-SHA256署名を生成"""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def dispatch(
        webhook: Webhook,
        event: str,
        data: dict,
        db: AsyncSession,
    ) -> WebhookLog:
        """Webhookを送信"""
        payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
        }

        if webhook.secret:
            signature = WebhookDispatcher.generate_signature(payload_json, webhook.secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        log = WebhookLog(
            webhook_id=webhook.id,
            event=event,
            payload=payload,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    webhook.url,
                    content=payload_json,
                    headers=headers,
                )
                log.status_code = response.status_code
                log.response_body = response.text[:1000]  # 最大1000文字

        except httpx.TimeoutException:
            log.error_message = "Timeout: リクエストがタイムアウトしました"
        except httpx.RequestError as e:
            log.error_message = f"Request error: {str(e)}"
        except Exception as e:
            log.error_message = f"Unexpected error: {str(e)}"

        db.add(log)
        await db.flush()
        return log


async def trigger_webhooks(
    db: AsyncSession,
    user_id: uuid.UUID,
    event: str,
    data: dict,
):
    """特定イベントの全Webhookを発火"""
    query = select(Webhook).where(
        Webhook.user_id == user_id,
        Webhook.is_active == True,
    )
    result = await db.execute(query)
    webhooks = result.scalars().all()

    for webhook in webhooks:
        if event in webhook.events:
            await WebhookDispatcher.dispatch(webhook, event, data, db)


async def notify_transcription_event(
    db: AsyncSession,
    transcription: Transcription,
    event: str,
):
    """文字起こしイベントをWebhookで通知"""
    data = {
        "transcription_id": str(transcription.id),
        "title": transcription.title,
        "status": transcription.status,
        "language": transcription.language,
        "audio_duration_sec": transcription.audio_duration_sec,
        "created_at": transcription.created_at.isoformat() if transcription.created_at else None,
    }

    if event == "transcription.failed":
        data["error_message"] = transcription.error_message

    await trigger_webhooks(db, transcription.user_id, event, data)
