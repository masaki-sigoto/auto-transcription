"""モニタリング・アラート・ログ集約サービス"""

import os
import json
import time
import logging
import traceback
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
import asyncio
import httpx


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    SLACK = "slack"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass
class LogEntry:
    """構造化ログエントリ"""
    timestamp: datetime
    level: LogLevel
    message: str
    logger_name: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_json(self) -> str:
        """JSON形式に変換"""
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "logger": self.logger_name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "extra": self.extra,
            "exception": self.exception,
            "stack_trace": self.stack_trace,
        }, ensure_ascii=False)


@dataclass
class Alert:
    """アラート"""
    id: str
    name: str
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricPoint:
    """メトリクスポイント"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram


class StructuredLogger:
    """構造化ロガー"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self._context: Dict[str, Any] = {}

    def with_context(self, **kwargs) -> "StructuredLogger":
        """コンテキストを追加"""
        new_logger = StructuredLogger(self.name)
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _log(
        self,
        level: LogLevel,
        message: str,
        exc_info: Optional[Exception] = None,
        **kwargs,
    ) -> LogEntry:
        """ログを記録"""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=level,
            message=message,
            logger_name=self.name,
            trace_id=self._context.get("trace_id"),
            span_id=self._context.get("span_id"),
            user_id=self._context.get("user_id"),
            request_id=self._context.get("request_id"),
            extra={**self._context, **kwargs},
        )

        if exc_info:
            entry.exception = str(exc_info)
            entry.stack_trace = traceback.format_exc()

        # 標準ロガーに出力
        log_method = getattr(self.logger, level.value)
        log_method(entry.to_json())

        return entry

    def debug(self, message: str, **kwargs) -> LogEntry:
        return self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> LogEntry:
        return self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> LogEntry:
        return self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: Optional[Exception] = None, **kwargs) -> LogEntry:
        return self._log(LogLevel.ERROR, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: Optional[Exception] = None, **kwargs) -> LogEntry:
        return self._log(LogLevel.CRITICAL, message, exc_info=exc_info, **kwargs)


class PrometheusMetrics:
    """Prometheusメトリクス"""

    def __init__(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._labels: Dict[str, Dict[str, str]] = {}

    def counter(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None):
        """カウンターをインクリメント"""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value
        if labels:
            self._labels[key] = labels

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """ゲージを設定"""
        key = self._make_key(name, labels)
        self._gauges[key] = value
        if labels:
            self._labels[key] = labels

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """ヒストグラムに追加"""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        if labels:
            self._labels[key] = labels

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def export_prometheus(self) -> str:
        """Prometheus形式でエクスポート"""
        lines = []

        # カウンター
        for key, value in self._counters.items():
            lines.append(f"{key} {value}")

        # ゲージ
        for key, value in self._gauges.items():
            lines.append(f"{key} {value}")

        # ヒストグラム（簡略版）
        for key, values in self._histograms.items():
            if values:
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")

        return "\n".join(lines)


class AlertManager:
    """アラートマネージャー"""

    def __init__(self):
        self._alerts: List[Alert] = []
        self._channels: Dict[AlertChannel, Dict[str, Any]] = {}
        self._rules: List[Dict[str, Any]] = []

    def configure_channel(
        self,
        channel: AlertChannel,
        config: Dict[str, Any],
    ):
        """アラートチャンネルを設定"""
        self._channels[channel] = config

    def add_rule(
        self,
        name: str,
        condition: Callable[[], bool],
        severity: AlertSeverity,
        message: str,
        channels: List[AlertChannel],
    ):
        """アラートルールを追加"""
        self._rules.append({
            "name": name,
            "condition": condition,
            "severity": severity,
            "message": message,
            "channels": channels,
        })

    async def trigger_alert(
        self,
        name: str,
        severity: AlertSeverity,
        message: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """アラートをトリガー"""
        import uuid

        alert = Alert(
            id=str(uuid.uuid4()),
            name=name,
            severity=severity,
            message=message,
            source=source,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

        self._alerts.append(alert)

        # 通知を送信
        await self._send_notifications(alert)

        return alert

    async def _send_notifications(self, alert: Alert):
        """通知を送信"""
        for channel, config in self._channels.items():
            try:
                if channel == AlertChannel.SLACK:
                    await self._send_slack(alert, config)
                elif channel == AlertChannel.EMAIL:
                    await self._send_email(alert, config)
                elif channel == AlertChannel.PAGERDUTY:
                    await self._send_pagerduty(alert, config)
                elif channel == AlertChannel.WEBHOOK:
                    await self._send_webhook(alert, config)
            except Exception as e:
                logging.error(f"Failed to send alert to {channel}: {e}")

    async def _send_slack(self, alert: Alert, config: Dict[str, Any]):
        """Slack通知"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            return

        color_map = {
            AlertSeverity.LOW: "#36a64f",
            AlertSeverity.MEDIUM: "#ffcc00",
            AlertSeverity.HIGH: "#ff9900",
            AlertSeverity.CRITICAL: "#ff0000",
        }

        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json={
                    "attachments": [
                        {
                            "color": color_map.get(alert.severity, "#808080"),
                            "title": f"[{alert.severity.value.upper()}] {alert.name}",
                            "text": alert.message,
                            "fields": [
                                {"title": "Source", "value": alert.source, "short": True},
                                {"title": "Time", "value": alert.timestamp.isoformat(), "short": True},
                            ],
                        }
                    ]
                },
                timeout=10,
            )

    async def _send_email(self, alert: Alert, config: Dict[str, Any]):
        """メール通知（実装はプレースホルダー）"""
        pass

    async def _send_pagerduty(self, alert: Alert, config: Dict[str, Any]):
        """PagerDuty通知"""
        routing_key = config.get("routing_key")
        if not routing_key:
            return

        severity_map = {
            AlertSeverity.LOW: "info",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "error",
            AlertSeverity.CRITICAL: "critical",
        }

        async with httpx.AsyncClient() as client:
            await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json={
                    "routing_key": routing_key,
                    "event_action": "trigger",
                    "payload": {
                        "summary": f"{alert.name}: {alert.message}",
                        "severity": severity_map.get(alert.severity, "info"),
                        "source": alert.source,
                        "timestamp": alert.timestamp.isoformat(),
                    },
                },
                timeout=10,
            )

    async def _send_webhook(self, alert: Alert, config: Dict[str, Any]):
        """Webhook通知"""
        url = config.get("url")
        if not url:
            return

        async with httpx.AsyncClient() as client:
            await client.post(
                url,
                json={
                    "id": alert.id,
                    "name": alert.name,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "source": alert.source,
                    "timestamp": alert.timestamp.isoformat(),
                    "metadata": alert.metadata,
                },
                timeout=10,
            )

    def resolve_alert(self, alert_id: str) -> bool:
        """アラートを解決済みにする"""
        for alert in self._alerts:
            if alert.id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.utcnow()
                return True
        return False

    def get_active_alerts(self) -> List[Alert]:
        """アクティブなアラートを取得"""
        return [a for a in self._alerts if not a.resolved]


class SentryIntegration:
    """Sentry統合"""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("SENTRY_DSN")
        self._initialized = False

    def init(self):
        """Sentryを初期化"""
        if not self.dsn:
            return

        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=self.dsn,
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
            )
            self._initialized = True
        except ImportError:
            logging.warning("sentry-sdk not installed")

    def capture_exception(self, exception: Exception, extra: Optional[Dict[str, Any]] = None):
        """例外をキャプチャ"""
        if not self._initialized:
            return

        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                if extra:
                    for key, value in extra.items():
                        scope.set_extra(key, value)
                sentry_sdk.capture_exception(exception)
        except ImportError:
            pass

    def capture_message(self, message: str, level: str = "info"):
        """メッセージをキャプチャ"""
        if not self._initialized:
            return

        try:
            import sentry_sdk
            sentry_sdk.capture_message(message, level=level)
        except ImportError:
            pass


class RequestTracer:
    """リクエストトレーサー"""

    def __init__(self):
        self._traces: Dict[str, Dict[str, Any]] = {}

    def start_trace(self, trace_id: str, name: str) -> Dict[str, Any]:
        """トレースを開始"""
        trace = {
            "trace_id": trace_id,
            "name": name,
            "start_time": time.perf_counter(),
            "spans": [],
        }
        self._traces[trace_id] = trace
        return trace

    def add_span(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        start_time: float,
        end_time: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """スパンを追加"""
        if trace_id not in self._traces:
            return

        self._traces[trace_id]["spans"].append({
            "span_id": span_id,
            "name": name,
            "duration_ms": (end_time - start_time) * 1000,
            "metadata": metadata or {},
        })

    def end_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """トレースを終了"""
        if trace_id not in self._traces:
            return None

        trace = self._traces.pop(trace_id)
        trace["end_time"] = time.perf_counter()
        trace["total_duration_ms"] = (trace["end_time"] - trace["start_time"]) * 1000
        return trace


# グローバルインスタンス
metrics = PrometheusMetrics()
alert_manager = AlertManager()
sentry = SentryIntegration()
tracer = RequestTracer()


def get_logger(name: str) -> StructuredLogger:
    """構造化ロガーを取得"""
    return StructuredLogger(name)


def track_request(func: Callable) -> Callable:
    """リクエストトラッキングデコレータ"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        import uuid
        trace_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        try:
            result = await func(*args, **kwargs)
            metrics.counter("http_requests_total", labels={"status": "success"})
            return result
        except Exception as e:
            metrics.counter("http_requests_total", labels={"status": "error"})
            sentry.capture_exception(e)
            raise
        finally:
            duration = time.perf_counter() - start_time
            metrics.histogram("http_request_duration_seconds", duration)

    return wrapper
