import uuid
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService, DashboardService

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================

class UsageSummaryResponse(BaseModel):
    total_transcriptions: int
    total_duration_sec: int
    total_characters: int
    total_words: int
    total_api_calls: int
    total_tokens: int
    total_storage_bytes: int


class UsageTrendItem(BaseModel):
    date: str
    transcriptions: int
    duration_sec: int
    words: int


class TranscriptionAnalyticsResponse(BaseModel):
    transcription_id: uuid.UUID
    total_duration_sec: int
    total_segments: int
    total_words: int
    total_characters: int
    unique_words: int
    speaker_count: int
    speaker_stats: dict
    speaking_rate_wpm: Optional[float]
    filler_word_count: int
    keywords: list[dict]
    overall_confidence: Optional[float]


class CreateReportRequest(BaseModel):
    name: str
    report_type: str
    config: dict
    description: Optional[str] = None
    team_id: Optional[uuid.UUID] = None
    schedule: Optional[dict] = None


class ReportResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    report_type: str
    config: dict
    schedule: Optional[dict]
    last_run_at: Optional[str]
    created_at: str


class DashboardResponse(BaseModel):
    monthly_usage: dict
    weekly_trend: list[dict]
    recent_transcriptions: list[dict]
    top_speakers: list[dict]


# =============================================================================
# 使用量統計
# =============================================================================

@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """使用量サマリーを取得"""
    if not start_date:
        start_date = date.today().replace(day=1)
    if not end_date:
        end_date = date.today()

    service = AnalyticsService(db)
    summary = await service.get_usage_summary(user_id, start_date, end_date)

    return UsageSummaryResponse(
        total_transcriptions=summary['total_transcriptions'],
        total_duration_sec=summary['total_duration_sec'],
        total_characters=summary['total_characters'],
        total_words=summary['total_words'],
        total_api_calls=summary['total_api_calls'],
        total_tokens=summary['total_tokens'],
        total_storage_bytes=summary['total_storage_bytes'],
    )


@router.get("/usage/trend", response_model=list[UsageTrendItem])
async def get_usage_trend(
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    group_by: str = Query(default='day', regex='^(day|week|month)$'),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """使用量トレンドを取得"""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()

    service = AnalyticsService(db)
    trend = await service.get_usage_trend(user_id, start_date, end_date, group_by)

    return [UsageTrendItem(**item) for item in trend]


# =============================================================================
# 文字起こし分析
# =============================================================================

@router.post("/transcriptions/{transcription_id}/analyze", response_model=TranscriptionAnalyticsResponse)
async def analyze_transcription(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしを分析"""
    service = AnalyticsService(db)

    try:
        analytics = await service.analyze_transcription(transcription_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return TranscriptionAnalyticsResponse(
        transcription_id=analytics.transcription_id,
        total_duration_sec=analytics.total_duration_sec,
        total_segments=analytics.total_segments,
        total_words=analytics.total_words,
        total_characters=analytics.total_characters,
        unique_words=analytics.unique_words,
        speaker_count=analytics.speaker_count,
        speaker_stats=analytics.speaker_stats or {},
        speaking_rate_wpm=analytics.speaking_rate_wpm,
        filler_word_count=analytics.filler_word_count,
        keywords=analytics.keywords or [],
        overall_confidence=analytics.overall_confidence,
    )


@router.get("/transcriptions/{transcription_id}/analytics", response_model=TranscriptionAnalyticsResponse)
async def get_transcription_analytics(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こし分析を取得"""
    service = AnalyticsService(db)
    analytics = await service.get_transcription_analytics(transcription_id)

    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics not found")

    return TranscriptionAnalyticsResponse(
        transcription_id=analytics.transcription_id,
        total_duration_sec=analytics.total_duration_sec,
        total_segments=analytics.total_segments,
        total_words=analytics.total_words,
        total_characters=analytics.total_characters,
        unique_words=analytics.unique_words,
        speaker_count=analytics.speaker_count,
        speaker_stats=analytics.speaker_stats or {},
        speaking_rate_wpm=analytics.speaking_rate_wpm,
        filler_word_count=analytics.filler_word_count,
        keywords=analytics.keywords or [],
        overall_confidence=analytics.overall_confidence,
    )


# =============================================================================
# レポート
# =============================================================================

@router.post("/reports", response_model=ReportResponse, status_code=201)
async def create_report(
    request: CreateReportRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レポートを作成"""
    service = AnalyticsService(db)
    report = await service.create_report(
        user_id=user_id,
        name=request.name,
        report_type=request.report_type,
        config=request.config,
        description=request.description,
        team_id=request.team_id,
        schedule=request.schedule,
    )

    return ReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        report_type=report.report_type,
        config=report.config,
        schedule=report.schedule,
        last_run_at=report.last_run_at.isoformat() if report.last_run_at else None,
        created_at=report.created_at.isoformat(),
    )


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レポート一覧を取得"""
    service = AnalyticsService(db)
    reports = await service.list_reports(user_id, team_id)

    return [
        ReportResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            report_type=r.report_type,
            config=r.config,
            schedule=r.schedule,
            last_run_at=r.last_run_at.isoformat() if r.last_run_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in reports
    ]


@router.post("/reports/{report_id}/run")
async def run_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レポートを実行"""
    service = AnalyticsService(db)

    try:
        result = await service.run_report(report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return result


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """レポートを削除"""
    service = AnalyticsService(db)
    if not await service.delete_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found")


# =============================================================================
# ダッシュボード
# =============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ダッシュボード統計を取得"""
    service = DashboardService(db)
    stats = await service.get_dashboard_stats(user_id)

    return DashboardResponse(**stats)
