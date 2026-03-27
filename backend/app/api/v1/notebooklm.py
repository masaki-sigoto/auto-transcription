"""NotebookLM連携APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.notebooklm_service import (
    NotebookLMService,
    ExportFormat,
)

router = APIRouter(prefix="/notebooklm", tags=["notebooklm"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === エクスポート ===

class ExportRequest(BaseModel):
    transcription_id: str
    format: ExportFormat = ExportFormat.MARKDOWN
    include_timestamps: bool = True
    include_speakers: bool = True


@router.post("/export")
async def export_for_notebooklm(
    request: ExportRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """NotebookLM用にエクスポート"""
    # 実際の実装ではDBから文字起こしを取得
    transcription_data = {
        "id": request.transcription_id,
        "title": "サンプル会議",
        "created_at": datetime.utcnow().isoformat(),
        "audio_duration_sec": 3600,
        "language": "ja",
        "summary": "これはサンプルの会議の要約です。主要な議題について話し合いました。",
        "speakers": [
            {"id": "speaker_1", "label": "話者1", "name": "田中"},
            {"id": "speaker_2", "label": "話者2", "name": "佐藤"},
        ],
        "segments": [
            {
                "start_time_ms": 0,
                "end_time_ms": 5000,
                "text": "本日はお集まりいただきありがとうございます。",
                "speaker_id": "speaker_1",
            },
            {
                "start_time_ms": 5000,
                "end_time_ms": 10000,
                "text": "それでは、議題に入りましょう。",
                "speaker_id": "speaker_2",
            },
        ],
    }

    service = NotebookLMService()

    result = await service.export_for_notebooklm(
        transcription_data,
        format=request.format,
        include_timestamps=request.include_timestamps,
        include_speakers=request.include_speakers,
    )

    return result


@router.get("/export/{transcription_id}/download")
async def download_export(
    transcription_id: str,
    format: ExportFormat = Query(ExportFormat.MARKDOWN),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """エクスポートファイルをダウンロード"""
    # 実際の実装ではDBから文字起こしを取得
    transcription_data = {
        "id": transcription_id,
        "title": "サンプル会議",
        "created_at": datetime.utcnow().isoformat(),
        "audio_duration_sec": 3600,
        "language": "ja",
        "speakers": [],
        "segments": [
            {
                "start_time_ms": 0,
                "end_time_ms": 5000,
                "text": "サンプルテキスト",
            },
        ],
    }

    service = NotebookLMService()
    result = await service.export_for_notebooklm(transcription_data, format=format)

    # Content-Typeを設定
    content_types = {
        ExportFormat.MARKDOWN: "text/markdown",
        ExportFormat.TXT: "text/plain",
        ExportFormat.JSON: "application/json",
    }

    return Response(
        content=result["content"],
        media_type=content_types.get(format, "text/plain"),
        headers={
            "Content-Disposition": f"attachment; filename={result['filename']}",
        },
    )


# === ポッドキャストスクリプト生成 ===

class PodcastScriptRequest(BaseModel):
    transcription_id: str
    style: str = "conversational"  # conversational, formal, casual
    target_duration_min: int = 10


@router.post("/podcast-script")
async def generate_podcast_script(
    request: PodcastScriptRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ポッドキャストスクリプトを生成（Audio Overview風）"""
    # 実際の実装ではDBから文字起こしを取得
    transcription_data = {
        "id": request.transcription_id,
        "title": "サンプル会議",
        "summary": "新製品の開発進捗について話し合いました。",
        "segments": [
            {
                "start_time_ms": 0,
                "end_time_ms": 10000,
                "text": "今日は新製品の進捗について話しましょう。",
            },
        ],
    }

    service = NotebookLMService()

    result = await service.generate_podcast_script(
        transcription_data,
        style=request.style,
        target_duration_min=request.target_duration_min,
    )

    return result


# === 学習ガイド生成 ===

@router.post("/study-guide/{transcription_id}")
async def generate_study_guide(
    transcription_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """学習ガイドを生成"""
    # 実際の実装ではDBから文字起こしを取得
    transcription_data = {
        "id": transcription_id,
        "title": "サンプル講義",
        "segments": [
            {"text": "今日の講義では、機械学習の基礎について学びます。"},
        ],
    }

    service = NotebookLMService()

    result = await service.generate_study_guide(transcription_data)

    return result


# === バッチエクスポート ===

class BatchExportRequest(BaseModel):
    transcription_ids: List[str]
    format: ExportFormat = ExportFormat.MARKDOWN


@router.post("/export/batch")
async def batch_export(
    request: BatchExportRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """複数の文字起こしをバッチエクスポート"""
    service = NotebookLMService()
    results = []

    for trans_id in request.transcription_ids:
        # 実際の実装ではDBから取得
        transcription_data = {
            "id": trans_id,
            "title": f"文字起こし {trans_id[:8]}",
            "segments": [],
        }

        result = await service.export_for_notebooklm(
            transcription_data,
            format=request.format,
        )
        results.append({
            "transcription_id": trans_id,
            **result,
        })

    return {
        "count": len(results),
        "format": request.format.value,
        "exports": results,
    }


# === フォーマット情報 ===

@router.get("/formats")
async def list_export_formats():
    """利用可能なエクスポート形式一覧"""
    return {
        "formats": [
            {
                "id": ExportFormat.MARKDOWN.value,
                "name": "Markdown",
                "description": "NotebookLMに最適。構造化されたテキスト形式",
                "extension": ".md",
                "recommended": True,
            },
            {
                "id": ExportFormat.TXT.value,
                "name": "Plain Text",
                "description": "シンプルなテキスト形式",
                "extension": ".txt",
                "recommended": False,
            },
            {
                "id": ExportFormat.JSON.value,
                "name": "JSON",
                "description": "メタデータを含む構造化データ",
                "extension": ".json",
                "recommended": False,
            },
            {
                "id": ExportFormat.PDF.value,
                "name": "PDF",
                "description": "印刷・共有に最適（未実装）",
                "extension": ".pdf",
                "recommended": False,
            },
            {
                "id": ExportFormat.GOOGLE_DOCS.value,
                "name": "Google Docs",
                "description": "Google Docsに直接エクスポート（未実装）",
                "extension": None,
                "recommended": True,
            },
        ]
    }


# === 使い方ガイド ===

@router.get("/guide")
async def get_usage_guide():
    """NotebookLM連携の使い方ガイド"""
    return {
        "title": "NotebookLM連携ガイド",
        "steps": [
            {
                "step": 1,
                "title": "文字起こしをエクスポート",
                "description": "Markdown形式でエクスポートするのがおすすめです",
                "endpoint": "POST /notebooklm/export",
            },
            {
                "step": 2,
                "title": "NotebookLMにアップロード",
                "description": "エクスポートしたファイルをNotebookLMのソースとして追加",
                "url": "https://notebooklm.google.com/",
            },
            {
                "step": 3,
                "title": "AIと対話",
                "description": "NotebookLMのAIに質問したり、要約を生成させる",
            },
            {
                "step": 4,
                "title": "Audio Overviewを生成",
                "description": "ポッドキャスト形式の音声要約を生成（NotebookLM機能）",
            },
        ],
        "tips": [
            "複数の文字起こしをまとめてアップロードすると、横断的な分析が可能",
            "議事録と関連資料を一緒にアップロードすると、より深い分析ができる",
            "ポッドキャストスクリプト機能で、事前にプレビューが可能",
        ],
    }
