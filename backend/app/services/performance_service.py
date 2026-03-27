"""パフォーマンス最適化・スケーリングサービス"""

import asyncio
import time
import os
import json
from typing import Optional, List, Dict, Any, Callable, TypeVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
import hashlib
import redis.asyncio as redis


T = TypeVar("T")


@dataclass
class CacheConfig:
    ttl_seconds: int = 300
    max_size: int = 1000
    namespace: str = "transcription"


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime
    hits: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


class LocalCache:
    """ローカルインメモリキャッシュ"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: List[str] = []

    def _make_key(self, key: str) -> str:
        return f"{self.config.namespace}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """キャッシュから取得"""
        full_key = self._make_key(key)
        entry = self._cache.get(full_key)

        if not entry:
            return None

        if entry.expires_at < datetime.utcnow():
            self.delete(key)
            return None

        entry.hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """キャッシュに設定"""
        full_key = self._make_key(key)
        ttl = ttl or self.config.ttl_seconds

        # LRU: サイズ制限を超えたら古いエントリを削除
        while len(self._cache) >= self.config.max_size:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)

        self._cache[full_key] = CacheEntry(
            value=value,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        )
        self._access_order.append(full_key)

    def delete(self, key: str) -> bool:
        """キャッシュから削除"""
        full_key = self._make_key(key)
        if full_key in self._cache:
            del self._cache[full_key]
            if full_key in self._access_order:
                self._access_order.remove(full_key)
            return True
        return False

    def clear(self, pattern: Optional[str] = None) -> int:
        """キャッシュをクリア"""
        if not pattern:
            count = len(self._cache)
            self._cache.clear()
            self._access_order.clear()
            return count

        prefix = self._make_key(pattern.rstrip("*"))
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
        return len(keys_to_delete)

    def stats(self) -> Dict[str, Any]:
        """キャッシュ統計"""
        total_hits = sum(e.hits for e in self._cache.values())
        return {
            "size": len(self._cache),
            "max_size": self.config.max_size,
            "total_hits": total_hits,
            "ttl_seconds": self.config.ttl_seconds,
        }


class RedisCache:
    """Redis分散キャッシュ"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        if not self._client:
            self._client = redis.from_url(self.redis_url)
        return self._client

    def _make_key(self, key: str) -> str:
        return f"{self.config.namespace}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """キャッシュから取得"""
        client = await self._get_client()
        full_key = self._make_key(key)

        value = await client.get(full_key)
        if value:
            return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """キャッシュに設定"""
        client = await self._get_client()
        full_key = self._make_key(key)
        ttl = ttl or self.config.ttl_seconds

        await client.set(full_key, json.dumps(value), ex=ttl)

    async def delete(self, key: str) -> bool:
        """キャッシュから削除"""
        client = await self._get_client()
        full_key = self._make_key(key)
        result = await client.delete(full_key)
        return result > 0

    async def clear(self, pattern: str = "*") -> int:
        """パターンにマッチするキャッシュをクリア"""
        client = await self._get_client()
        full_pattern = self._make_key(pattern)

        cursor = 0
        count = 0
        while True:
            cursor, keys = await client.scan(cursor, match=full_pattern, count=100)
            if keys:
                await client.delete(*keys)
                count += len(keys)
            if cursor == 0:
                break

        return count

    async def close(self) -> None:
        """接続を閉じる"""
        if self._client:
            await self._client.close()
            self._client = None


class CacheService:
    """統合キャッシュサービス"""

    def __init__(self, use_redis: bool = True):
        self.use_redis = use_redis and os.getenv("REDIS_URL")
        self.local_cache = LocalCache()
        self.redis_cache = RedisCache() if self.use_redis else None

    async def get(self, key: str) -> Optional[Any]:
        """キャッシュから取得（ローカル優先）"""
        # ローカルキャッシュをチェック
        value = self.local_cache.get(key)
        if value is not None:
            return value

        # Redisをチェック
        if self.redis_cache:
            value = await self.redis_cache.get(key)
            if value is not None:
                # ローカルキャッシュにも保存
                self.local_cache.set(key, value)
                return value

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """キャッシュに設定"""
        self.local_cache.set(key, value, ttl)

        if self.redis_cache:
            await self.redis_cache.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """キャッシュから削除"""
        result = self.local_cache.delete(key)

        if self.redis_cache:
            result = await self.redis_cache.delete(key) or result

        return result

    async def clear(self, pattern: str = "*") -> int:
        """キャッシュをクリア"""
        count = self.local_cache.clear(pattern)

        if self.redis_cache:
            count += await self.redis_cache.clear(pattern)

        return count


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    cache_service: Optional[CacheService] = None,
):
    """キャッシュデコレータ"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # キャッシュキーを生成
            key_parts = [key_prefix or func.__name__]
            key_parts.extend(str(a) for a in args[1:])  # self/clsをスキップ
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            service = cache_service or CacheService()

            # キャッシュをチェック
            cached_value = await service.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 関数を実行
            result = await func(*args, **kwargs)

            # 結果をキャッシュ
            await service.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


@dataclass
class PerformanceMetric:
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """メトリクス収集"""

    def __init__(self):
        self._metrics: List[PerformanceMetric] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """カウンターをインクリメント"""
        self._counters[name] += value
        self._metrics.append(PerformanceMetric(
            name=f"counter.{name}",
            value=float(value),
            timestamp=datetime.utcnow(),
            tags=tags or {},
        ))

    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """ゲージを設定"""
        self._gauges[name] = value
        self._metrics.append(PerformanceMetric(
            name=f"gauge.{name}",
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        ))

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """ヒストグラムに追加"""
        self._histograms[name].append(value)
        self._metrics.append(PerformanceMetric(
            name=f"histogram.{name}",
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        ))

    def timing(self, name: str):
        """タイミングデコレータ"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    self.histogram(f"{name}.duration_ms", (time.perf_counter() - start) * 1000)
                    self.increment(f"{name}.success")
                    return result
                except Exception as e:
                    self.histogram(f"{name}.duration_ms", (time.perf_counter() - start) * 1000)
                    self.increment(f"{name}.error", tags={"error": type(e).__name__})
                    raise

            return wrapper
        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """統計を取得"""
        stats = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }

        for name, values in self._histograms.items():
            if values:
                sorted_values = sorted(values)
                stats["histograms"][name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "p50": sorted_values[len(sorted_values) // 2],
                    "p95": sorted_values[int(len(sorted_values) * 0.95)] if len(sorted_values) > 1 else sorted_values[0],
                    "p99": sorted_values[int(len(sorted_values) * 0.99)] if len(sorted_values) > 1 else sorted_values[0],
                }

        return stats

    def reset(self) -> None:
        """メトリクスをリセット"""
        self._metrics.clear()
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


class ConnectionPool:
    """接続プール管理"""

    def __init__(
        self,
        min_size: int = 5,
        max_size: int = 20,
        acquire_timeout: float = 30.0,
    ):
        self.min_size = min_size
        self.max_size = max_size
        self.acquire_timeout = acquire_timeout
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._lock = asyncio.Lock()

    async def initialize(self, factory: Callable) -> None:
        """プールを初期化"""
        for _ in range(self.min_size):
            conn = await factory()
            await self._pool.put(conn)
            self._size += 1

    async def acquire(self, factory: Callable) -> Any:
        """接続を取得"""
        try:
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            pass

        async with self._lock:
            if self._size < self.max_size:
                conn = await factory()
                self._size += 1
                return conn

        # プールが満杯の場合は待機
        return await asyncio.wait_for(
            self._pool.get(),
            timeout=self.acquire_timeout,
        )

    async def release(self, conn: Any) -> None:
        """接続を返却"""
        await self._pool.put(conn)

    def stats(self) -> Dict[str, Any]:
        """プール統計"""
        return {
            "size": self._size,
            "available": self._pool.qsize(),
            "in_use": self._size - self._pool.qsize(),
            "min_size": self.min_size,
            "max_size": self.max_size,
        }


class RateLimiter:
    """レート制限"""

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst: int = 20,
    ):
        self.rate = requests_per_second
        self.burst = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """トークンを取得"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now

            # トークンを補充
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: float = 1.0) -> None:
        """トークンが利用可能になるまで待機"""
        while not await self.acquire(tokens):
            await asyncio.sleep(1.0 / self.rate)


class CircuitBreaker:
    """サーキットブレーカー"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half-open
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """保護された呼び出し"""
        async with self._lock:
            if self._state == "open":
                if self._last_failure_time and \
                   time.monotonic() - self._last_failure_time > self.recovery_timeout:
                    self._state = "half-open"
                    self._half_open_calls = 0
                else:
                    raise Exception("Circuit breaker is open")

            if self._state == "half-open":
                if self._half_open_calls >= self.half_open_max_calls:
                    raise Exception("Circuit breaker is half-open, max calls reached")
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)

            async with self._lock:
                if self._state == "half-open":
                    self._state = "closed"
                    self._failure_count = 0

            return result

        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()

                if self._failure_count >= self.failure_threshold:
                    self._state = "open"

            raise


class LoadBalancer:
    """ロードバランサー"""

    def __init__(self, strategy: str = "round_robin"):
        self.strategy = strategy
        self._servers: List[Dict[str, Any]] = []
        self._current_index = 0
        self._lock = asyncio.Lock()

    def add_server(
        self,
        host: str,
        port: int,
        weight: int = 1,
        health_check_url: Optional[str] = None,
    ) -> None:
        """サーバーを追加"""
        self._servers.append({
            "host": host,
            "port": port,
            "weight": weight,
            "health_check_url": health_check_url,
            "healthy": True,
            "connections": 0,
        })

    async def get_server(self) -> Optional[Dict[str, Any]]:
        """サーバーを取得"""
        async with self._lock:
            healthy_servers = [s for s in self._servers if s["healthy"]]

            if not healthy_servers:
                return None

            if self.strategy == "round_robin":
                server = healthy_servers[self._current_index % len(healthy_servers)]
                self._current_index += 1
                return server

            elif self.strategy == "least_connections":
                return min(healthy_servers, key=lambda s: s["connections"])

            elif self.strategy == "weighted":
                # 重み付きランダム
                import random
                total_weight = sum(s["weight"] for s in healthy_servers)
                rand = random.uniform(0, total_weight)
                current = 0
                for server in healthy_servers:
                    current += server["weight"]
                    if rand <= current:
                        return server

            return healthy_servers[0]

    async def health_check(self) -> Dict[str, Any]:
        """ヘルスチェック実行"""
        import httpx

        results = {}
        async with httpx.AsyncClient() as client:
            for server in self._servers:
                if server["health_check_url"]:
                    try:
                        url = f"http://{server['host']}:{server['port']}{server['health_check_url']}"
                        response = await client.get(url, timeout=5)
                        server["healthy"] = response.status_code == 200
                    except Exception:
                        server["healthy"] = False

                results[f"{server['host']}:{server['port']}"] = server["healthy"]

        return results


# グローバルインスタンス
metrics_collector = MetricsCollector()
cache_service = CacheService()
