"""高度な分析APIエンドポイント"""

import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.core.database import get_db
from app.services.advanced_analytics_service import (
    AdvancedAnalyticsService,
    ReportService,
    TrendPeriod,
)

router = APIRouter(prefix="/advanced-analytics", tags=["advanced-analytics"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class TrendResponse(BaseModel):
    period: str
    total_meetings: int
    total_duration_minutes: int
    avg_duration_minutes: float
    total_participants: int
    avg_participants: float


class SpeakerAnalysisResponse(BaseModel):
    speaker_id: str
    speaker_name: str
    total_speaking_time_seconds: float
    speaking_percentage: float
    word_count: int
    avg_words_per_minute: float
    sentiment_distribution: dict
    top_keywords: list[str]


class ProductivityResponse(BaseModel):
    team_id: str
    team_name: str
    period: str
    total_meetings: int
    total_meeting_hours: float
    action_items_created: int
    action_items_completed: int
    completion_rate: float
    avg_meeting_effectiveness: float
    meeting_cost_estimate: float
    recommendations: list[str]


class InsightResponse(BaseModel):
    insight_type: str
    title: str
    description: str
    severity: str
    data: dict
    recommendations: list[str]


@router.get("/trends", response_model=list[TrendResponse])
async def get_meeting_trends(
    period: str = Query("weekly", enum=["daily", "weekly", "monthly", "quarterly"]),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """会議トレンドを取得"""
    service = AdvancedAnalyticsService(db)

    team_uuid = None
    if team_id:
        try:
            team_uuid = uuid.UUID(team_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid team_id format")

    trends = await service.get_meeting_trends(
        user_id=user_id,
        team_id=team_uuid,
        period=TrendPeriod(period),
        start_date=start_date,
        end_date=end_date,
    )

    return [
        TrendResponse(
            period=t.period,
            total_meetings=t.total_meetings,
            total_duration_minutes=t.total_duration_minutes,
            avg_duration_minutes=t.avg_duration_minutes,
            total_participants=t.total_participants,
            avg_participants=t.avg_participants,
        )
        for t in trends
    ]


@router.get("/speakers/{transcription_id}", response_model=list[SpeakerAnalysisResponse])
async def analyze_speakers(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """話者分析を実行"""
    try:
        tid = uuid.UUID(transcription_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    service = AdvancedAnalyticsService(db)
    analyses = await service.analyze_speaker(tid)

    return [
        SpeakerAnalysisResponse(
            speaker_id=a.speaker_id,
            speaker_name=a.speaker_name,
            total_speaking_time_seconds=a.total_speaking_time_seconds,
            speaking_percentage=a.speaking_percentage,
            word_count=a.word_count,
            avg_words_per_minute=a.avg_words_per_minute,
            sentiment_distribution=a.sentiment_distribution,
            top_keywords=a.top_keywords,
        )
        for a in analyses
    ]


@router.get("/productivity/{team_id}", response_model=ProductivityResponse)
async def get_team_productivity(
    team_id: str,
    period: str = Query("monthly", enum=["weekly", "monthly", "quarterly"]),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チーム生産性を取得"""
    try:
        tid = uuid.UUID(team_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid team_id format")

    service = AdvancedAnalyticsService(db)
    productivity = await service.get_team_productivity(
        team_id=tid,
        period=TrendPeriod(period),
        start_date=start_date,
        end_date=end_date,
    )

    return ProductivityResponse(
        team_id=productivity.team_id,
        team_name=productivity.team_name,
        period=productivity.period,
        total_meetings=productivity.total_meetings,
        total_meeting_hours=productivity.total_meeting_hours,
        action_items_created=productivity.action_items_created,
        action_items_completed=productivity.action_items_completed,
        completion_rate=productivity.completion_rate,
        avg_meeting_effectiveness=productivity.avg_meeting_effectiveness,
        meeting_cost_estimate=productivity.meeting_cost_estimate,
        recommendations=productivity.recommendations,
    )


@router.get("/insights/{transcription_id}", response_model=list[InsightResponse])
async def get_meeting_insights(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """会議インサイトを取得"""
    try:
        tid = uuid.UUID(transcription_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    service = AdvancedAnalyticsService(db)
    insights = await service.generate_insights(tid)

    return [
        InsightResponse(
            insight_type=i.insight_type,
            title=i.title,
            description=i.description,
            severity=i.severity,
            data=i.data,
            recommendations=i.recommendations,
        )
        for i in insights
    ]


@router.get("/report")
async def generate_report(
    format: str = Query("json", enum=["json", "excel", "pdf"]),
    team_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レポートを生成"""
    team_uuid = None
    if team_id:
        try:
            team_uuid = uuid.UUID(team_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid team_id format")

    service = ReportService(db)
    report_data = await service.generate_summary_report(
        user_id=user_id,
        team_id=team_uuid,
        start_date=start_date,
        end_date=end_date,
    )

    if format == "json":
        return report_data

    elif format == "excel":
        excel_data = await service.export_to_excel(report_data)
        return StreamingResponse(
            io.BytesIO(excel_data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=report.xlsx"},
        )

    elif format == "pdf":
        pdf_data = await service.export_to_pdf(report_data)
        return StreamingResponse(
            io.BytesIO(pdf_data),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=report.pdf"},
        )


@router.get("/dashboard")
async def get_dashboard_data(
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ダッシュボード用データを取得"""
    service = AdvancedAnalyticsService(db)

    team_uuid = None
    if team_id:
        try:
            team_uuid = uuid.UUID(team_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid team_id format")

    # 今週のトレンド
    weekly_trends = await service.get_meeting_trends(
        user_id=user_id,
        team_id=team_uuid,
        period=TrendPeriod.DAILY,
    )

    # 今月のトレンド
    monthly_trends = await service.get_meeting_trends(
        user_id=user_id,
        team_id=team_uuid,
        period=TrendPeriod.WEEKLY,
    )

    # 統計サマリー
    total_meetings = sum(t.total_meetings for t in weekly_trends)
    total_duration = sum(t.total_duration_minutes for t in weekly_trends)
    avg_duration = total_duration / total_meetings if total_meetings > 0 else 0

    return {
        "summary": {
            "total_meetings_this_week": total_meetings,
            "total_duration_minutes": total_duration,
            "avg_duration_minutes": round(avg_duration, 1),
        },
        "weekly_trends": [
            {
                "period": t.period,
                "meetings": t.total_meetings,
                "duration": t.total_duration_minutes,
            }
            for t in weekly_trends[-7:]  # 直近7日
        ],
        "monthly_trends": [
            {
                "period": t.period,
                "meetings": t.total_meetings,
                "duration": t.total_duration_minutes,
            }
            for t in monthly_trends[-4:]  # 直近4週
        ],
    }


@router.get("/compare")
async def compare_periods(
    period1_start: datetime,
    period1_end: datetime,
    period2_start: datetime,
    period2_end: datetime,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """期間比較"""
    service = AdvancedAnalyticsService(db)

    team_uuid = None
    if team_id:
        try:
            team_uuid = uuid.UUID(team_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid team_id format")

    # 期間1のデータ
    trends1 = await service.get_meeting_trends(
        user_id=user_id,
        team_id=team_uuid,
        period=TrendPeriod.DAILY,
        start_date=period1_start,
        end_date=period1_end,
    )

    # 期間2のデータ
    trends2 = await service.get_meeting_trends(
        user_id=user_id,
        team_id=team_uuid,
        period=TrendPeriod.DAILY,
        start_date=period2_start,
        end_date=period2_end,
    )

    # 集計
    total1 = sum(t.total_meetings for t in trends1)
    total2 = sum(t.total_meetings for t in trends2)
    duration1 = sum(t.total_duration_minutes for t in trends1)
    duration2 = sum(t.total_duration_minutes for t in trends2)

    # 変化率計算
    meeting_change = ((total2 - total1) / total1 * 100) if total1 > 0 else 0
    duration_change = ((duration2 - duration1) / duration1 * 100) if duration1 > 0 else 0

    return {
        "period1": {
            "start": period1_start.isoformat(),
            "end": period1_end.isoformat(),
            "total_meetings": total1,
            "total_duration_minutes": duration1,
        },
        "period2": {
            "start": period2_start.isoformat(),
            "end": period2_end.isoformat(),
            "total_meetings": total2,
            "total_duration_minutes": duration2,
        },
        "comparison": {
            "meeting_change_percent": round(meeting_change, 1),
            "duration_change_percent": round(duration_change, 1),
        },
    }
