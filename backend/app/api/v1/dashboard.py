"""高度なレポート・ダッシュボードAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.dashboard_service import (
    dashboard_analytics_engine,
    dashboard_manager,
    report_generator,
    TimeRange,
    MetricType,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def get_current_tenant_id() -> str:
    return "default-tenant"


# =====================
# 概要メトリクス
# =====================

@router.get("/metrics")
async def get_overview_metrics(
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """概要メトリクスを取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    metrics = await dashboard_analytics_engine.get_overview_metrics(tenant_id, tr)

    return {
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "change_percent": m.change_percent,
                "change_direction": m.change_direction,
                "previous_value": m.previous_value,
            }
            for m in metrics
        ],
        "time_range": time_range,
    }


# =====================
# チャートデータ
# =====================

@router.get("/charts/transcription-trend")
async def get_transcription_trend(
    time_range: str = "last_30_days",
    granularity: str = "day",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こしトレンドを取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    chart = await dashboard_analytics_engine.get_transcription_trend(
        tenant_id, tr, granularity
    )

    return {
        "chart_type": chart.chart_type.value,
        "title": chart.title,
        "series": [
            {
                "label": s.label,
                "color": s.color,
                "data": [
                    {"x": t.isoformat(), "y": v}
                    for t, v in zip(s.timestamps, s.values)
                ],
            }
            for s in chart.series
        ],
        "x_axis_label": chart.x_axis_label,
        "y_axis_label": chart.y_axis_label,
    }


@router.get("/charts/duration-distribution")
async def get_duration_distribution(
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """録音時間分布を取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    chart = await dashboard_analytics_engine.get_duration_distribution(tenant_id, tr)

    return {
        "chart_type": chart.chart_type.value,
        "title": chart.title,
        "categories": chart.metadata.get("categories", []),
        "values": chart.series[0].values if chart.series else [],
    }


@router.get("/charts/speaker-distribution")
async def get_speaker_distribution(
    transcription_id: Optional[str] = None,
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """話者分布を取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    speakers = await dashboard_analytics_engine.get_speaker_analytics(
        tenant_id, transcription_id, tr
    )

    return {
        "chart_type": "pie",
        "title": "話者発言時間分布",
        "data": [
            {
                "name": s.speaker_name,
                "value": s.speaking_percentage,
                "speaking_time_sec": s.total_speaking_time_sec,
            }
            for s in speakers
        ],
    }


# =====================
# 話者分析
# =====================

@router.get("/speakers")
async def get_speaker_analytics(
    transcription_id: Optional[str] = None,
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """話者分析を取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    speakers = await dashboard_analytics_engine.get_speaker_analytics(
        tenant_id, transcription_id, tr
    )

    return {
        "speakers": [
            {
                "id": s.speaker_id,
                "name": s.speaker_name,
                "total_speaking_time_sec": s.total_speaking_time_sec,
                "word_count": s.word_count,
                "segment_count": s.segment_count,
                "speaking_percentage": s.speaking_percentage,
                "avg_segment_duration_sec": s.avg_segment_duration_sec,
                "sentiment": s.sentiment_scores,
            }
            for s in speakers
        ],
        "count": len(speakers),
    }


# =====================
# 会議統計
# =====================

@router.get("/meetings")
async def get_meeting_statistics(
    time_range: str = "last_30_days",
    limit: int = Query(default=20, le=100),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """会議統計を取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    meetings = await dashboard_analytics_engine.get_meeting_statistics(tenant_id, tr)

    return {
        "meetings": [
            {
                "id": m.meeting_id,
                "title": m.title,
                "date": m.date.isoformat(),
                "duration_sec": m.duration_sec,
                "duration_min": m.duration_sec // 60,
                "participant_count": m.participant_count,
                "word_count": m.word_count,
                "action_item_count": m.action_item_count,
                "sentiment": m.sentiment_summary,
            }
            for m in meetings[:limit]
        ],
        "count": len(meetings),
    }


# =====================
# 生産性レポート
# =====================

@router.get("/productivity")
async def get_productivity_report(
    time_range: str = "last_30_days",
    user_id: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """生産性レポートを取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    report = await dashboard_analytics_engine.get_productivity_report(
        tenant_id, tr, user_id
    )

    return {
        "period": {
            "start": report.period_start.isoformat(),
            "end": report.period_end.isoformat(),
        },
        "total_meetings": report.total_meetings,
        "total_meeting_time_hours": report.total_meeting_time_hours,
        "avg_meeting_duration_min": report.avg_meeting_duration_min,
        "action_items": {
            "created": report.action_items_created,
            "completed": report.action_items_completed,
            "completion_rate": report.completion_rate,
        },
        "patterns": {
            "most_active_days": report.most_active_days,
            "peak_hours": report.peak_hours,
        },
    }


# =====================
# トレンド分析
# =====================

@router.get("/trends/{metric}")
async def get_trend_analysis(
    metric: str,
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """トレンド分析を取得"""
    try:
        metric_type = MetricType(metric)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")

    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    analysis = await dashboard_analytics_engine.get_trend_analysis(
        tenant_id, metric_type, tr
    )

    return {
        "metric": analysis.metric,
        "current_value": analysis.current_value,
        "trend": {
            "direction": analysis.trend_direction,
            "percentage": analysis.trend_percentage,
        },
        "forecast": {
            "next_period": analysis.forecast_next_period,
        },
        "seasonality_detected": analysis.seasonality_detected,
        "anomalies": analysis.anomalies,
    }


# =====================
# ダッシュボード管理
# =====================

class CreateDashboardRequest(BaseModel):
    name: str
    description: str = ""
    widgets: List[dict] = []


@router.post("/dashboards")
async def create_dashboard(
    request: CreateDashboardRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ダッシュボードを作成"""
    dashboard = await dashboard_manager.create_dashboard(
        tenant_id=tenant_id,
        name=request.name,
        description=request.description,
        widgets=request.widgets,
    )

    return {
        "id": dashboard["id"],
        "name": dashboard["name"],
        "description": dashboard["description"],
        "widget_count": len(dashboard["widgets"]),
        "created_at": dashboard["created_at"].isoformat(),
    }


@router.get("/dashboards")
async def list_dashboards(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ダッシュボード一覧"""
    dashboards = await dashboard_manager.list_dashboards(tenant_id)

    return {
        "dashboards": [
            {
                "id": d["id"],
                "name": d["name"],
                "description": d["description"],
                "widget_count": len(d["widgets"]),
                "created_at": d["created_at"].isoformat(),
                "updated_at": d["updated_at"].isoformat(),
            }
            for d in dashboards
        ],
        "count": len(dashboards),
    }


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard(
    dashboard_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ダッシュボードを取得"""
    dashboard = await dashboard_manager.get_dashboard(dashboard_id)

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    return {
        "id": dashboard["id"],
        "name": dashboard["name"],
        "description": dashboard["description"],
        "widgets": dashboard["widgets"],
        "created_at": dashboard["created_at"].isoformat(),
        "updated_at": dashboard["updated_at"].isoformat(),
    }


class AddWidgetRequest(BaseModel):
    widget_type: str
    title: str
    config: dict = {}
    position: Optional[dict] = None


@router.post("/dashboards/{dashboard_id}/widgets")
async def add_widget(
    dashboard_id: str,
    request: AddWidgetRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ウィジェットを追加"""
    widget = await dashboard_manager.add_widget(
        dashboard_id=dashboard_id,
        widget_type=request.widget_type,
        title=request.title,
        config=request.config,
        position=request.position,
    )

    return {
        "id": widget["id"],
        "type": widget["type"],
        "title": widget["title"],
        "position": widget["position"],
    }


@router.get("/widgets/{widget_id}/data")
async def get_widget_data(
    widget_id: str,
    time_range: str = "last_30_days",
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ウィジェットデータを取得"""
    try:
        tr = TimeRange(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time_range: {time_range}")

    try:
        data = await dashboard_manager.get_widget_data(widget_id, tr)
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =====================
# レポート生成
# =====================

@router.post("/reports/weekly")
async def generate_weekly_report(
    include_charts: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """週次レポートを生成"""
    report = await report_generator.generate_weekly_report(
        tenant_id, include_charts
    )

    return report


@router.post("/reports/monthly")
async def generate_monthly_report(
    include_charts: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """月次レポートを生成"""
    report = await report_generator.generate_monthly_report(
        tenant_id, include_charts
    )

    return report


# =====================
# 利用可能な設定
# =====================

@router.get("/time-ranges")
async def list_time_ranges():
    """利用可能な時間範囲"""
    return {
        "time_ranges": [
            {"id": "today", "name": "今日"},
            {"id": "yesterday", "name": "昨日"},
            {"id": "last_7_days", "name": "過去7日間"},
            {"id": "last_30_days", "name": "過去30日間"},
            {"id": "last_90_days", "name": "過去90日間"},
            {"id": "this_month", "name": "今月"},
            {"id": "last_month", "name": "先月"},
            {"id": "this_year", "name": "今年"},
            {"id": "custom", "name": "カスタム期間"},
        ]
    }


@router.get("/metrics-types")
async def list_metric_types():
    """利用可能なメトリクスタイプ"""
    return {
        "metrics": [
            {"id": "transcription_count", "name": "文字起こし数"},
            {"id": "total_duration", "name": "総録音時間"},
            {"id": "word_count", "name": "総単語数"},
            {"id": "speaker_count", "name": "話者数"},
            {"id": "meeting_count", "name": "会議数"},
            {"id": "active_users", "name": "アクティブユーザー"},
        ]
    }


@router.get("/widget-types")
async def list_widget_types():
    """利用可能なウィジェットタイプ"""
    return {
        "widget_types": [
            {"id": "overview_metrics", "name": "概要メトリクス", "description": "主要KPIを表示"},
            {"id": "transcription_trend", "name": "文字起こしトレンド", "description": "時系列の文字起こし数"},
            {"id": "duration_distribution", "name": "録音時間分布", "description": "録音時間の分布"},
            {"id": "speaker_analytics", "name": "話者分析", "description": "話者別の発言統計"},
            {"id": "productivity_report", "name": "生産性レポート", "description": "生産性指標"},
            {"id": "meeting_list", "name": "会議リスト", "description": "最近の会議一覧"},
        ]
    }
