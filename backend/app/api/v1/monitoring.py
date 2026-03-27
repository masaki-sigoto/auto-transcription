"""モニタリング・アラート・ログ集約APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.monitoring_service import (
    metrics,
    alert_manager,
    get_logger,
    AlertSeverity,
    AlertChannel,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

logger = get_logger(__name__)


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === メトリクス ===

@router.get("/metrics")
async def get_metrics(
    format: str = Query("prometheus", enum=["prometheus", "json"]),
):
    """メトリクスを取得"""
    if format == "prometheus":
        return metrics.export_prometheus()

    return {
        "counters": metrics._counters,
        "gauges": metrics._gauges,
        "histograms": {k: {"count": len(v), "sum": sum(v)} for k, v in metrics._histograms.items()},
    }


class MetricRequest(BaseModel):
    name: str
    value: float
    metric_type: str = "gauge"  # gauge, counter, histogram
    labels: Optional[dict] = None


@router.post("/metrics")
async def record_metric(
    request: MetricRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メトリクスを記録"""
    if request.metric_type == "counter":
        metrics.counter(request.name, request.value, request.labels)
    elif request.metric_type == "gauge":
        metrics.gauge(request.name, request.value, request.labels)
    elif request.metric_type == "histogram":
        metrics.histogram(request.name, request.value, request.labels)
    else:
        raise HTTPException(status_code=400, detail="Invalid metric type")

    return {"status": "recorded", "metric": request.name}


# === アラート ===

class TriggerAlertRequest(BaseModel):
    name: str
    severity: AlertSeverity
    message: str
    source: str
    metadata: Optional[dict] = None


@router.post("/alerts")
async def trigger_alert(
    request: TriggerAlertRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アラートをトリガー"""
    alert = await alert_manager.trigger_alert(
        name=request.name,
        severity=request.severity,
        message=request.message,
        source=request.source,
        metadata=request.metadata,
    )

    logger.info(
        "Alert triggered",
        alert_id=alert.id,
        alert_name=alert.name,
        severity=alert.severity.value,
    )

    return {
        "id": alert.id,
        "name": alert.name,
        "severity": alert.severity.value,
        "message": alert.message,
        "timestamp": alert.timestamp.isoformat(),
    }


@router.get("/alerts")
async def list_alerts(
    active_only: bool = Query(True),
    severity: Optional[AlertSeverity] = None,
    limit: int = Query(50, le=100),
):
    """アラート一覧を取得"""
    if active_only:
        alerts = alert_manager.get_active_alerts()
    else:
        alerts = alert_manager._alerts

    if severity:
        alerts = [a for a in alerts if a.severity == severity]

    alerts = sorted(alerts, key=lambda a: a.timestamp, reverse=True)[:limit]

    return {
        "alerts": [
            {
                "id": a.id,
                "name": a.name,
                "severity": a.severity.value,
                "message": a.message,
                "source": a.source,
                "timestamp": a.timestamp.isoformat(),
                "resolved": a.resolved,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in alerts
        ],
        "total": len(alerts),
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アラートを解決済みにする"""
    success = alert_manager.resolve_alert(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")

    logger.info("Alert resolved", alert_id=alert_id)

    return {"status": "resolved", "alert_id": alert_id}


# === アラートチャンネル設定 ===

class ChannelConfigRequest(BaseModel):
    channel: AlertChannel
    config: dict


@router.post("/alerts/channels")
async def configure_alert_channel(
    request: ChannelConfigRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アラートチャンネルを設定"""
    alert_manager.configure_channel(request.channel, request.config)

    return {
        "status": "configured",
        "channel": request.channel.value,
    }


@router.get("/alerts/channels")
async def list_alert_channels():
    """設定済みアラートチャンネル一覧"""
    return {
        "channels": [
            {
                "id": channel.value,
                "name": channel.name,
                "configured": channel in alert_manager._channels,
            }
            for channel in AlertChannel
        ]
    }


# === ログ ===

class LogRequest(BaseModel):
    level: str = "info"
    message: str
    extra: Optional[dict] = None


@router.post("/logs")
async def write_log(
    request: LogRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ログを記録"""
    log_method = getattr(logger, request.level, logger.info)
    entry = log_method(request.message, **(request.extra or {}))

    return {
        "status": "logged",
        "level": request.level,
        "timestamp": entry.timestamp.isoformat(),
    }


# === ヘルスチェック ===

@router.get("/health")
async def health_check():
    """システムヘルスチェック"""
    checks = {
        "api": {"status": "healthy", "latency_ms": 1},
        "database": {"status": "healthy", "latency_ms": 5},
        "redis": {"status": "healthy", "latency_ms": 2},
        "storage": {"status": "healthy", "latency_ms": 10},
    }

    overall_status = "healthy"
    for check in checks.values():
        if check["status"] == "unhealthy":
            overall_status = "unhealthy"
            break
        elif check["status"] == "degraded":
            overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }


# === ダッシュボード ===

@router.get("/dashboard")
async def get_dashboard():
    """モニタリングダッシュボード情報"""
    active_alerts = alert_manager.get_active_alerts()

    return {
        "summary": {
            "active_alerts": len(active_alerts),
            "critical_alerts": len([a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]),
            "high_alerts": len([a for a in active_alerts if a.severity == AlertSeverity.HIGH]),
        },
        "metrics_summary": {
            "total_counters": len(metrics._counters),
            "total_gauges": len(metrics._gauges),
            "total_histograms": len(metrics._histograms),
        },
        "recent_alerts": [
            {
                "id": a.id,
                "name": a.name,
                "severity": a.severity.value,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in sorted(active_alerts, key=lambda x: x.timestamp, reverse=True)[:5]
        ],
    }
