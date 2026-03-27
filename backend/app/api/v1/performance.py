"""パフォーマンス監視・最適化APIエンドポイント"""

import uuid
import time
import psutil
import os
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.performance_service import (
    CacheService,
    MetricsCollector,
    metrics_collector,
    cache_service,
)

router = APIRouter(prefix="/performance", tags=["performance"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === システムメトリクス ===

@router.get("/system")
async def get_system_metrics(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """システムメトリクスを取得"""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # プロセス情報
    process = psutil.Process(os.getpid())
    process_memory = process.memory_info()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count(),
            "count_logical": psutil.cpu_count(logical=True),
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent": memory.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": round(disk.percent, 1),
        },
        "process": {
            "pid": os.getpid(),
            "memory_mb": round(process_memory.rss / (1024**2), 2),
            "cpu_percent": process.cpu_percent(),
            "threads": process.num_threads(),
        },
    }


# === アプリケーションメトリクス ===

@router.get("/metrics")
async def get_application_metrics(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アプリケーションメトリクスを取得"""
    return metrics_collector.get_stats()


@router.post("/metrics/reset")
async def reset_metrics(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メトリクスをリセット"""
    metrics_collector.reset()
    return {"status": "reset", "timestamp": datetime.utcnow().isoformat()}


# === キャッシュ管理 ===

@router.get("/cache/stats")
async def get_cache_stats(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャッシュ統計を取得"""
    local_stats = cache_service.local_cache.stats()

    return {
        "local_cache": local_stats,
        "redis_enabled": cache_service.redis_cache is not None,
    }


class CacheSetRequest(BaseModel):
    key: str
    value: dict
    ttl: Optional[int] = 300


@router.post("/cache")
async def set_cache(
    request: CacheSetRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャッシュを設定"""
    await cache_service.set(request.key, request.value, request.ttl)
    return {"status": "set", "key": request.key, "ttl": request.ttl}


@router.get("/cache/{key}")
async def get_cache(
    key: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャッシュを取得"""
    value = await cache_service.get(key)

    if value is None:
        raise HTTPException(status_code=404, detail="Cache key not found")

    return {"key": key, "value": value}


@router.delete("/cache/{key}")
async def delete_cache(
    key: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャッシュを削除"""
    deleted = await cache_service.delete(key)
    return {"status": "deleted" if deleted else "not_found", "key": key}


@router.post("/cache/clear")
async def clear_cache(
    pattern: str = Query("*"),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャッシュをクリア"""
    count = await cache_service.clear(pattern)
    return {"status": "cleared", "pattern": pattern, "count": count}


# === ヘルスチェック ===

@router.get("/health")
async def health_check():
    """ヘルスチェック"""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # データベース接続チェック
    try:
        # 実際の実装ではDBクエリを実行
        checks["checks"]["database"] = {"status": "healthy", "latency_ms": 1}
    except Exception as e:
        checks["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        checks["status"] = "unhealthy"

    # Redisチェック
    if cache_service.redis_cache:
        try:
            start = time.perf_counter()
            await cache_service.redis_cache.set("health_check", "ok", 10)
            latency = (time.perf_counter() - start) * 1000
            checks["checks"]["redis"] = {"status": "healthy", "latency_ms": round(latency, 2)}
        except Exception as e:
            checks["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
            checks["status"] = "degraded"

    # メモリチェック
    memory = psutil.virtual_memory()
    if memory.percent > 90:
        checks["checks"]["memory"] = {"status": "warning", "percent": memory.percent}
        if checks["status"] == "healthy":
            checks["status"] = "degraded"
    else:
        checks["checks"]["memory"] = {"status": "healthy", "percent": memory.percent}

    return checks


@router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    # 実際の実装では依存サービスの準備状態をチェック
    return {"status": "ready"}


# === パフォーマンステスト ===

@router.get("/benchmark/echo")
async def benchmark_echo(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """エコーベンチマーク（最小レイテンシ計測用）"""
    return {"timestamp": datetime.utcnow().isoformat()}


@router.get("/benchmark/cpu")
async def benchmark_cpu(
    iterations: int = Query(1000000, le=10000000),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """CPUベンチマーク"""
    start = time.perf_counter()

    # 単純な計算
    result = 0
    for i in range(iterations):
        result += i * i

    duration_ms = (time.perf_counter() - start) * 1000

    return {
        "iterations": iterations,
        "duration_ms": round(duration_ms, 2),
        "ops_per_second": round(iterations / (duration_ms / 1000)),
    }


@router.get("/benchmark/memory")
async def benchmark_memory(
    size_mb: int = Query(10, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メモリベンチマーク"""
    start = time.perf_counter()

    # メモリ確保
    data = bytearray(size_mb * 1024 * 1024)

    allocation_ms = (time.perf_counter() - start) * 1000

    # クリーンアップ
    del data

    return {
        "size_mb": size_mb,
        "allocation_ms": round(allocation_ms, 2),
        "mb_per_second": round(size_mb / (allocation_ms / 1000), 2),
    }


# === レート制限状態 ===

@router.get("/rate-limits")
async def get_rate_limit_status(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レート制限状態を取得"""
    # 実際の実装ではRateLimiterの状態を返す
    return {
        "user_id": str(user_id),
        "limits": {
            "requests_per_minute": 60,
            "requests_per_hour": 1000,
        },
        "current": {
            "requests_this_minute": 5,
            "requests_this_hour": 100,
        },
        "remaining": {
            "this_minute": 55,
            "this_hour": 900,
        },
    }


# === サーキットブレーカー状態 ===

@router.get("/circuit-breakers")
async def get_circuit_breaker_status(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """サーキットブレーカー状態を取得"""
    # 実際の実装では各サービスのサーキットブレーカー状態を返す
    return {
        "services": {
            "transcription_engine": {
                "state": "closed",
                "failure_count": 0,
                "last_failure": None,
            },
            "ai_service": {
                "state": "closed",
                "failure_count": 0,
                "last_failure": None,
            },
            "storage_service": {
                "state": "closed",
                "failure_count": 0,
                "last_failure": None,
            },
        }
    }


# === 設定 ===

@router.get("/config")
async def get_performance_config(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """パフォーマンス設定を取得"""
    return {
        "cache": {
            "local_max_size": 1000,
            "default_ttl_seconds": 300,
            "redis_enabled": cache_service.redis_cache is not None,
        },
        "rate_limiting": {
            "enabled": True,
            "strategy": "token_bucket",
        },
        "circuit_breaker": {
            "enabled": True,
            "failure_threshold": 5,
            "recovery_timeout_seconds": 30,
        },
        "connection_pool": {
            "min_size": 5,
            "max_size": 20,
        },
    }
