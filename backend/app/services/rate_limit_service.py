"""レート制限・API課金サービス"""

import time
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import get_settings

settings = get_settings()


class RateLimitTier(str, Enum):
    """レート制限ティア"""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass
class RateLimitConfig:
    """レート制限設定"""
    tier: RateLimitTier
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    max_file_size_mb: int
    max_duration_minutes: int
    concurrent_jobs: int


# ティアごとの制限
RATE_LIMIT_CONFIGS = {
    RateLimitTier.FREE: RateLimitConfig(
        tier=RateLimitTier.FREE,
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=500,
        max_file_size_mb=25,
        max_duration_minutes=30,
        concurrent_jobs=1,
    ),
    RateLimitTier.STARTER: RateLimitConfig(
        tier=RateLimitTier.STARTER,
        requests_per_minute=30,
        requests_per_hour=500,
        requests_per_day=5000,
        max_file_size_mb=100,
        max_duration_minutes=120,
        concurrent_jobs=3,
    ),
    RateLimitTier.PROFESSIONAL: RateLimitConfig(
        tier=RateLimitTier.PROFESSIONAL,
        requests_per_minute=100,
        requests_per_hour=2000,
        requests_per_day=20000,
        max_file_size_mb=500,
        max_duration_minutes=480,
        concurrent_jobs=10,
    ),
    RateLimitTier.ENTERPRISE: RateLimitConfig(
        tier=RateLimitTier.ENTERPRISE,
        requests_per_minute=500,
        requests_per_hour=10000,
        requests_per_day=100000,
        max_file_size_mb=2000,
        max_duration_minutes=1440,
        concurrent_jobs=50,
    ),
}


@dataclass
class RateLimitResult:
    """レート制限チェック結果"""
    allowed: bool
    remaining: int
    reset_at: datetime
    limit: int
    retry_after: Optional[int] = None


@dataclass
class APIUsage:
    """API使用量"""
    user_id: str
    period: str
    request_count: int
    transcription_minutes: float
    storage_bytes: int
    api_calls_by_endpoint: Dict[str, int]


class RateLimitService:
    """レート制限サービス"""

    def __init__(self):
        self.redis = redis.from_url(
            getattr(settings, 'redis_url', 'redis://localhost:6379'),
            encoding="utf-8",
            decode_responses=True,
        )

    async def check_rate_limit(
        self,
        user_id: UUID,
        tier: RateLimitTier,
        endpoint: str,
    ) -> RateLimitResult:
        """レート制限をチェック"""
        config = RATE_LIMIT_CONFIGS[tier]
        now = time.time()

        # 分単位のキー
        minute_key = f"ratelimit:{user_id}:minute:{int(now // 60)}"
        hour_key = f"ratelimit:{user_id}:hour:{int(now // 3600)}"
        day_key = f"ratelimit:{user_id}:day:{int(now // 86400)}"

        # パイプラインで効率的に取得
        pipe = self.redis.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 60)
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)

        results = await pipe.execute()

        minute_count = results[0]
        hour_count = results[2]
        day_count = results[4]

        # 制限チェック
        if minute_count > config.requests_per_minute:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=60 - (now % 60)),
                limit=config.requests_per_minute,
                retry_after=int(60 - (now % 60)),
            )

        if hour_count > config.requests_per_hour:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=3600 - (now % 3600)),
                limit=config.requests_per_hour,
                retry_after=int(3600 - (now % 3600)),
            )

        if day_count > config.requests_per_day:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=86400 - (now % 86400)),
                limit=config.requests_per_day,
                retry_after=int(86400 - (now % 86400)),
            )

        # エンドポイント別の使用量を記録
        endpoint_key = f"usage:{user_id}:endpoint:{endpoint}:{int(now // 86400)}"
        await self.redis.incr(endpoint_key)
        await self.redis.expire(endpoint_key, 86400 * 7)  # 7日間保持

        return RateLimitResult(
            allowed=True,
            remaining=config.requests_per_minute - minute_count,
            reset_at=datetime.utcnow() + timedelta(seconds=60 - (now % 60)),
            limit=config.requests_per_minute,
        )

    async def check_concurrent_jobs(
        self,
        user_id: UUID,
        tier: RateLimitTier,
    ) -> bool:
        """同時実行ジョブ数をチェック"""
        config = RATE_LIMIT_CONFIGS[tier]
        key = f"concurrent_jobs:{user_id}"

        current = await self.redis.get(key)
        current_count = int(current) if current else 0

        return current_count < config.concurrent_jobs

    async def increment_concurrent_jobs(self, user_id: UUID) -> int:
        """同時実行ジョブをインクリメント"""
        key = f"concurrent_jobs:{user_id}"
        count = await self.redis.incr(key)
        await self.redis.expire(key, 3600)  # 1時間でリセット
        return count

    async def decrement_concurrent_jobs(self, user_id: UUID) -> int:
        """同時実行ジョブをデクリメント"""
        key = f"concurrent_jobs:{user_id}"
        count = await self.redis.decr(key)
        if count < 0:
            await self.redis.set(key, 0)
            return 0
        return count

    async def get_usage_stats(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """使用量統計を取得"""
        now = time.time()

        minute_key = f"ratelimit:{user_id}:minute:{int(now // 60)}"
        hour_key = f"ratelimit:{user_id}:hour:{int(now // 3600)}"
        day_key = f"ratelimit:{user_id}:day:{int(now // 86400)}"

        pipe = self.redis.pipeline()
        pipe.get(minute_key)
        pipe.get(hour_key)
        pipe.get(day_key)

        results = await pipe.execute()

        return {
            "requests_this_minute": int(results[0] or 0),
            "requests_this_hour": int(results[1] or 0),
            "requests_today": int(results[2] or 0),
        }


class APIBillingService:
    """API課金サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = redis.from_url(
            getattr(settings, 'redis_url', 'redis://localhost:6379'),
            encoding="utf-8",
            decode_responses=True,
        )

    # 料金設定（円）
    PRICING = {
        "transcription_per_minute": 5,  # 1分あたり
        "storage_per_gb_month": 100,  # 1GBあたり月額
        "api_call": 0.01,  # 1コールあたり
        "ai_analysis": 10,  # 1回あたり
    }

    async def record_usage(
        self,
        user_id: UUID,
        usage_type: str,
        quantity: float,
        metadata: Optional[Dict] = None,
    ) -> str:
        """使用量を記録"""
        usage_id = str(uuid4())
        now = datetime.utcnow()

        await self.db.execute(
            text("""
                INSERT INTO api_usage (id, user_id, usage_type, quantity, unit_price, total_price, metadata, created_at)
                VALUES (:id, :user_id, :usage_type, :quantity, :unit_price, :total_price, :metadata, :created_at)
            """),
            {
                "id": usage_id,
                "user_id": str(user_id),
                "usage_type": usage_type,
                "quantity": quantity,
                "unit_price": self.PRICING.get(usage_type, 0),
                "total_price": quantity * self.PRICING.get(usage_type, 0),
                "metadata": json.dumps(metadata or {}),
                "created_at": now,
            },
        )
        await self.db.commit()

        # リアルタイム集計更新
        month_key = f"billing:{user_id}:{now.strftime('%Y-%m')}"
        await self.redis.hincrbyfloat(month_key, usage_type, quantity)
        await self.redis.expire(month_key, 86400 * 45)  # 45日間保持

        return usage_id

    async def get_monthly_usage(
        self,
        user_id: UUID,
        year: int,
        month: int,
    ) -> APIUsage:
        """月間使用量を取得"""
        month_key = f"billing:{user_id}:{year:04d}-{month:02d}"

        # Redisからリアルタイム集計を取得
        usage_data = await self.redis.hgetall(month_key)

        # DBから詳細を取得
        result = await self.db.execute(
            text("""
                SELECT usage_type, SUM(quantity) as total, COUNT(*) as count
                FROM api_usage
                WHERE user_id = :user_id
                AND created_at >= :start_date
                AND created_at < :end_date
                GROUP BY usage_type
            """),
            {
                "user_id": str(user_id),
                "start_date": datetime(year, month, 1),
                "end_date": datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1),
            },
        )
        rows = result.fetchall()

        api_calls_by_type = {row[0]: row[1] for row in rows}

        return APIUsage(
            user_id=str(user_id),
            period=f"{year:04d}-{month:02d}",
            request_count=sum(int(v) for v in usage_data.values()) if usage_data else 0,
            transcription_minutes=float(usage_data.get("transcription_per_minute", 0)),
            storage_bytes=0,  # 別途計算
            api_calls_by_endpoint=api_calls_by_type,
        )

    async def calculate_monthly_bill(
        self,
        user_id: UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """月間請求額を計算"""
        usage = await self.get_monthly_usage(user_id, year, month)

        line_items = []
        total = 0

        # 文字起こし料金
        transcription_cost = usage.transcription_minutes * self.PRICING["transcription_per_minute"]
        if transcription_cost > 0:
            line_items.append({
                "description": "文字起こし",
                "quantity": usage.transcription_minutes,
                "unit": "分",
                "unit_price": self.PRICING["transcription_per_minute"],
                "total": transcription_cost,
            })
            total += transcription_cost

        # API呼び出し料金
        api_cost = usage.request_count * self.PRICING["api_call"]
        if api_cost > 0:
            line_items.append({
                "description": "APIコール",
                "quantity": usage.request_count,
                "unit": "回",
                "unit_price": self.PRICING["api_call"],
                "total": api_cost,
            })
            total += api_cost

        # ストレージ料金
        storage_gb = usage.storage_bytes / (1024 ** 3)
        storage_cost = storage_gb * self.PRICING["storage_per_gb_month"]
        if storage_cost > 0:
            line_items.append({
                "description": "ストレージ",
                "quantity": round(storage_gb, 2),
                "unit": "GB",
                "unit_price": self.PRICING["storage_per_gb_month"],
                "total": storage_cost,
            })
            total += storage_cost

        return {
            "user_id": str(user_id),
            "period": f"{year:04d}-{month:02d}",
            "line_items": line_items,
            "subtotal": total,
            "tax": total * 0.1,  # 消費税10%
            "total": total * 1.1,
            "currency": "JPY",
        }

    async def get_usage_history(
        self,
        user_id: UUID,
        months: int = 6,
    ) -> List[Dict[str, Any]]:
        """使用量履歴を取得"""
        now = datetime.utcnow()
        history = []

        for i in range(months):
            date = now - timedelta(days=30 * i)
            usage = await self.get_monthly_usage(user_id, date.year, date.month)
            bill = await self.calculate_monthly_bill(user_id, date.year, date.month)

            history.append({
                "period": f"{date.year:04d}-{date.month:02d}",
                "request_count": usage.request_count,
                "transcription_minutes": usage.transcription_minutes,
                "total_cost": bill["total"],
            })

        return history


class WebhookService:
    """Webhookサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_webhook(
        self,
        user_id: UUID,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
    ) -> str:
        """Webhookを登録"""
        import secrets

        webhook_id = str(uuid4())
        webhook_secret = secret or secrets.token_urlsafe(32)

        await self.db.execute(
            text("""
                INSERT INTO webhooks (id, user_id, url, events, secret, is_active, created_at)
                VALUES (:id, :user_id, :url, :events, :secret, true, :created_at)
            """),
            {
                "id": webhook_id,
                "user_id": str(user_id),
                "url": url,
                "events": json.dumps(events),
                "secret": webhook_secret,
                "created_at": datetime.utcnow(),
            },
        )
        await self.db.commit()

        return webhook_id

    async def send_webhook(
        self,
        user_id: UUID,
        event: str,
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Webhookを送信"""
        import httpx
        import hmac
        import hashlib

        # 登録されたWebhookを取得
        result = await self.db.execute(
            text("""
                SELECT id, url, secret FROM webhooks
                WHERE user_id = :user_id AND is_active = true
                AND :event = ANY(SELECT jsonb_array_elements_text(events::jsonb))
            """),
            {"user_id": str(user_id), "event": event},
        )
        webhooks = result.fetchall()

        results = []
        payload_json = json.dumps(payload)

        async with httpx.AsyncClient() as client:
            for webhook in webhooks:
                webhook_id, url, secret = webhook

                # 署名を生成
                signature = hmac.new(
                    secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256,
                ).hexdigest()

                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-Webhook-Signature": f"sha256={signature}",
                            "X-Webhook-Event": event,
                        },
                        timeout=10.0,
                    )

                    results.append({
                        "webhook_id": webhook_id,
                        "status": "success",
                        "status_code": response.status_code,
                    })

                except Exception as e:
                    results.append({
                        "webhook_id": webhook_id,
                        "status": "error",
                        "error": str(e),
                    })

        return results

    async def get_webhooks(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Webhook一覧を取得"""
        result = await self.db.execute(
            text("""
                SELECT id, url, events, is_active, created_at
                FROM webhooks
                WHERE user_id = :user_id
            """),
            {"user_id": str(user_id)},
        )

        return [
            {
                "id": row[0],
                "url": row[1],
                "events": json.loads(row[2]),
                "is_active": row[3],
                "created_at": row[4],
            }
            for row in result.fetchall()
        ]
