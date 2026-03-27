import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.transcription import (
    TranscriptionCreate,
    TranscriptionUpdate,
    TranscriptionResponse,
    TranscriptionDetailResponse,
    TranscriptionListResponse,
    TranscriptionJobResponse,
    SegmentUpdate,
    SegmentResponse,
    ExportRequest,
    ExportResponse,
)
from app.services.transcription_service import TranscriptionService
from app.services.export_service import ExportService, get_export_content_type

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


@router.post("", response_model=TranscriptionJobResponse, status_code=202)
async def create_transcription(
    data: TranscriptionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新規文字起こしジョブを作成"""
    service = TranscriptionService(db)
    transcription = await service.create(current_user.id, data)

    # Celeryタスクで文字起こし処理を開始
    from app.worker import process_transcription
    process_transcription.delay(str(transcription.id))

    # 推定完了時間を計算（仮: 音声長の1/3）
    estimated_sec = None
    if transcription.audio_duration_sec:
        estimated_sec = transcription.audio_duration_sec // 3

    return TranscriptionJobResponse(
        id=transcription.id,
        status=transcription.status,
        estimated_completion_sec=estimated_sec,
    )


@router.get("", response_model=TranscriptionListResponse)
async def list_transcriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文字起こし一覧を取得"""
    service = TranscriptionService(db)
    transcriptions, total = await service.list_by_user(current_user.id, page, per_page)

    return TranscriptionListResponse(
        items=[TranscriptionResponse.model_validate(t) for t in transcriptions],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{transcription_id}", response_model=TranscriptionDetailResponse)
async def get_transcription(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文字起こし詳細を取得"""
    service = TranscriptionService(db)
    transcription = await service.get_by_id(transcription_id, current_user.id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return TranscriptionDetailResponse.model_validate(transcription)


@router.patch("/{transcription_id}", response_model=TranscriptionResponse)
async def update_transcription(
    transcription_id: uuid.UUID,
    data: TranscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文字起こしを更新（タイトル等）"""
    service = TranscriptionService(db)
    transcription = await service.update(transcription_id, current_user.id, data)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return TranscriptionResponse.model_validate(transcription)


@router.delete("/{transcription_id}", status_code=204)
async def delete_transcription(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文字起こしを削除"""
    service = TranscriptionService(db)
    deleted = await service.delete(transcription_id, current_user.id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Transcription not found")


@router.put("/segments/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: uuid.UUID,
    data: SegmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """セグメント（テキスト）を編集"""
    service = TranscriptionService(db)
    segment = await service.update_segment(segment_id, data)

    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    return SegmentResponse.model_validate(segment)


@router.post("/{transcription_id}/export", response_model=ExportResponse)
async def export_transcription(
    transcription_id: uuid.UUID,
    data: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """エクスポート（SRT/VTT/DOCX等）"""
    service = TranscriptionService(db)
    transcription = await service.get_by_id(transcription_id, current_user.id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    export_service = ExportService()

    # フォーマットに応じてエクスポート
    if data.format == "txt":
        content = export_service.export_txt(transcription.segments, transcription.speakers)
    elif data.format == "srt":
        content = export_service.export_srt(transcription.segments)
    elif data.format == "vtt":
        content = export_service.export_vtt(transcription.segments)
    elif data.format == "json":
        content = export_service.export_json(transcription.segments, transcription.speakers)
    elif data.format == "docx":
        content = export_service.export_docx(
            transcription.segments, transcription.speakers, transcription.title or ""
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {data.format}")

    # TODO: S3にアップロードして署名付きURLを返す
    # 一旦、仮のURLを返す
    return ExportResponse(
        download_url=f"/api/v1/transcriptions/{transcription_id}/download?format={data.format}",
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )


@router.post("/{transcription_id}/summarize")
async def summarize_transcription(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI要約を生成"""
    service = TranscriptionService(db)
    transcription = await service.get_by_id(transcription_id, current_user.id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    if not transcription.segments:
        raise HTTPException(status_code=400, detail="No segments to summarize")

    from app.services.llm_corrector import LLMCorrector
    from app.services.transcription_engine import TranscriptionSegment

    corrector = LLMCorrector()
    segments = [
        TranscriptionSegment(
            start_time_ms=s.start_time_ms,
            end_time_ms=s.end_time_ms,
            text=s.text,
        )
        for s in transcription.segments
    ]

    summary = await corrector.generate_summary(segments)
    return summary
