import json
import hashlib
from typing import Optional, Any, Callable
from datetime import timedelta
from functools import wraps
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()


class CacheManager:
    """Redis キャッシュマネージャー"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def get_redis(self) -> redis.Redis:
        """Redis接続を取得"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        """接続を閉じる"""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        """キャッシュを取得"""
        client = await self.get_redis()
        value = await client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
    ) -> bool:
        """キャッシュを設定"""
        client = await self.get_redis()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return await client.set(key, value, ex=expire)

    async def delete(self, key: str) -> int:
        """キャッシュを削除"""
        client = await self.get_redis()
        return await client.delete(key)

    async def delete_pattern(self, pattern: str) -> int:
        """パターンに一致するキャッシュを削除"""
        client = await self.get_redis()
        keys = await client.keys(pattern)
        if keys:
            return await client.delete(*keys)
        return 0

    async def exists(self, key: str) -> bool:
        """キャッシュが存在するか確認"""
        client = await self.get_redis()
        return await client.exists(key) > 0

    async def ttl(self, key: str) -> int:
        """残りTTLを取得"""
        client = await self.get_redis()
        return await client.ttl(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        """カウンターをインクリメント"""
        client = await self.get_redis()
        return await client.incr(key, amount)

    async def expire(self, key: str, seconds: int) -> bool:
        """有効期限を設定"""
        client = await self.get_redis()
        return await client.expire(key, seconds)

    # ===========================================================================
    # 高レベルメソッド
    # ===========================================================================

    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        expire: Optional[int] = 3600,
    ) -> Any:
        """キャッシュを取得、なければ生成して設定"""
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory() if callable(factory) else factory
        await self.set(key, value, expire)
        return value

    async def invalidate_user_cache(self, user_id: str):
        """ユーザー関連のキャッシュを無効化"""
        await self.delete_pattern(f"user:{user_id}:*")

    async def invalidate_transcription_cache(self, transcription_id: str):
        """文字起こし関連のキャッシュを無効化"""
        await self.delete_pattern(f"transcription:{transcription_id}:*")


# シングルトンインスタンス
cache_manager = CacheManager()


def cache_key(*args, **kwargs) -> str:
    """キャッシュキーを生成"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(
    prefix: str,
    expire: int = 3600,
    key_builder: Optional[Callable] = None,
):
    """キャッシュデコレーター"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # キャッシュキーを生成
            if key_builder:
                cache_suffix = key_builder(*args, **kwargs)
            else:
                cache_suffix = cache_key(*args[1:], **kwargs)  # selfを除外

            full_key = f"{prefix}:{cache_suffix}"

            # キャッシュを確認
            cached_value = await cache_manager.get(full_key)
            if cached_value is not None:
                return cached_value

            # 関数を実行
            result = await func(*args, **kwargs)

            # キャッシュに保存
            if result is not None:
                await cache_manager.set(full_key, result, expire)

            return result

        return wrapper
    return decorator


class RateLimiter:
    """レート制限"""

    def __init__(self, cache: CacheManager):
        self.cache = cache

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """
        レート制限をチェック

        Returns:
            tuple: (allowed, remaining, reset_seconds)
        """
        current = await self.cache.incr(key)

        if current == 1:
            await self.cache.expire(key, window_seconds)

        remaining = max(0, limit - current)
        ttl = await self.cache.ttl(key)
        reset_seconds = ttl if ttl > 0 else window_seconds

        return current <= limit, remaining, reset_seconds

    async def get_limit_info(
        self,
        key: str,
        limit: int,
    ) -> dict:
        """レート制限情報を取得"""
        current = await self.cache.get(key) or 0
        remaining = max(0, limit - int(current))
        ttl = await self.cache.ttl(key)

        return {
            "limit": limit,
            "remaining": remaining,
            "reset_seconds": ttl if ttl > 0 else 0,
        }


rate_limiter = RateLimiter(cache_manager)
