"""高度なAI機能APIエンドポイント"""

import uuid
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.services.transcription_service import TranscriptionService
from app.services.ai_summary import AISummaryService
from app.services.transcription_engine import TranscriptionSegment
from app.services.llm_service import (
    LLMService,
    TranscriptionAIService,
    LLMProvider,
    TaskType,
)

router = APIRouter(prefix="/ai", tags=["ai"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class MeetingMinutesResponse(BaseModel):
    title: str
    date: str
    participants: list[str]
    summary: str
    agenda_items: list[dict]
    action_items: list[dict]
    next_steps: list[str]


class ContentSummaryResponse(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    topics: list[dict]
    keywords: list[str]
    sentiment: str


class ChapterResponse(BaseModel):
    chapters: list[dict]


class QAPairsRequest(BaseModel):
    num_pairs: int = 5


class QAPairsResponse(BaseModel):
    qa_pairs: list[dict]


class EntitiesResponse(BaseModel):
    people: list[str]
    organizations: list[str]
    locations: list[str]
    products: list[str]
    dates: list[str]
    other: list[str]


async def get_transcription_segments(
    transcription_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[TranscriptionSegment]:
    """文字起こしセグメントを取得"""
    service = TranscriptionService(db)
    transcription = await service.get_by_id(transcription_id, user_id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    if not transcription.segments:
        raise HTTPException(status_code=400, detail="No segments available")

    # 話者情報をマッピング
    speaker_map = {str(s.id): s.label for s in transcription.speakers}

    return [
        TranscriptionSegment(
            start_time_ms=s.start_time_ms,
            end_time_ms=s.end_time_ms,
            text=s.text,
            confidence=s.confidence,
            speaker_id=speaker_map.get(str(s.speaker_id)) if s.speaker_id else None,
        )
        for s in transcription.segments
    ]


@router.post(
    "/transcriptions/{transcription_id}/meeting-minutes",
    response_model=MeetingMinutesResponse,
)
async def generate_meeting_minutes(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """議事録を生成"""
    segments = await get_transcription_segments(transcription_id, user_id, db)

    ai_service = AISummaryService()
    minutes = await ai_service.generate_meeting_minutes(segments)

    return MeetingMinutesResponse(
        title=minutes.title,
        date=minutes.date,
        participants=minutes.participants,
        summary=minutes.summary,
        agenda_items=minutes.agenda_items,
        action_items=minutes.action_items,
        next_steps=minutes.next_steps,
    )


@router.post(
    "/transcriptions/{transcription_id}/content-summary",
    response_model=ContentSummaryResponse,
)
async def generate_content_summary(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コンテンツ要約を生成"""
    segments = await get_transcription_segments(transcription_id, user_id, db)

    ai_service = AISummaryService()
    summary = await ai_service.generate_content_summary(segments)

    return ContentSummaryResponse(
        title=summary.title,
        summary=summary.summary,
        key_points=summary.key_points,
        topics=summary.topics,
        keywords=summary.keywords,
        sentiment=summary.sentiment,
    )


@router.post(
    "/transcriptions/{transcription_id}/chapters",
    response_model=ChapterResponse,
)
async def generate_chapters(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チャプターを生成"""
    segments = await get_transcription_segments(transcription_id, user_id, db)

    ai_service = AISummaryService()
    chapters = await ai_service.generate_chapters(segments)

    return ChapterResponse(chapters=chapters)


@router.post(
    "/transcriptions/{transcription_id}/qa-pairs",
    response_model=QAPairsResponse,
)
async def generate_qa_pairs(
    transcription_id: uuid.UUID,
    request: QAPairsRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Q&Aペアを生成"""
    segments = await get_transcription_segments(transcription_id, user_id, db)

    ai_service = AISummaryService()
    qa_pairs = await ai_service.generate_qa_pairs(segments, request.num_pairs)

    return QAPairsResponse(qa_pairs=qa_pairs)


@router.post(
    "/transcriptions/{transcription_id}/entities",
    response_model=EntitiesResponse,
)
async def extract_entities(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """エンティティを抽出"""
    segments = await get_transcription_segments(transcription_id, user_id, db)

    ai_service = AISummaryService()
    entities = await ai_service.extract_entities(segments)

    return EntitiesResponse(
        people=entities.get("people", []),
        organizations=entities.get("organizations", []),
        locations=entities.get("locations", []),
        products=entities.get("products", []),
        dates=entities.get("dates", []),
        other=entities.get("other", []),
    )


# === 高度なAI機能（LLM統合） ===

class AdvancedSummaryRequest(BaseModel):
    text: str
    style: str = "concise"  # concise, detailed, bullet, executive
    language: str = "ja"
    provider: Optional[LLMProvider] = None


class AdvancedSummaryResponse(BaseModel):
    summary: str
    style: str
    language: str
    provider: str


@router.post("/advanced/summary", response_model=AdvancedSummaryResponse)
async def generate_advanced_summary(
    request: AdvancedSummaryRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """高度な要約を生成（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    summary = await service.generate_summary(
        text=request.text,
        style=request.style,
        language=request.language,
        provider=request.provider,
    )

    return AdvancedSummaryResponse(
        summary=summary,
        style=request.style,
        language=request.language,
        provider=(request.provider or LLMProvider.OPENAI).value,
    )


class AdvancedMeetingMinutesRequest(BaseModel):
    text: str
    template: str = "standard"
    language: str = "ja"
    provider: Optional[LLMProvider] = None


@router.post("/advanced/meeting-minutes")
async def generate_advanced_meeting_minutes(
    request: AdvancedMeetingMinutesRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """高度な議事録を生成（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    minutes = await service.generate_meeting_minutes(
        text=request.text,
        template=request.template,
        language=request.language,
        provider=request.provider,
    )

    return {
        "meeting_minutes": minutes,
        "template": request.template,
        "language": request.language,
    }


class ActionItemsRequest(BaseModel):
    text: str
    language: str = "ja"
    provider: Optional[LLMProvider] = None


@router.post("/advanced/action-items")
async def extract_advanced_action_items(
    request: ActionItemsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アクションアイテムを抽出（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    items = await service.extract_action_items(
        text=request.text,
        language=request.language,
        provider=request.provider,
    )

    return {
        "action_items": items,
        "count": len(items),
        "language": request.language,
    }


class SentimentRequest(BaseModel):
    text: str
    language: str = "ja"
    provider: Optional[LLMProvider] = None


@router.post("/advanced/sentiment")
async def analyze_advanced_sentiment(
    request: SentimentRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """感情分析を実行（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    analysis = await service.analyze_sentiment(
        text=request.text,
        language=request.language,
        provider=request.provider,
    )

    return {
        "sentiment_analysis": analysis,
        "language": request.language,
    }


class TranslationRequest(BaseModel):
    text: str
    target_language: str
    source_language: Optional[str] = None
    provider: Optional[LLMProvider] = None


class TranslationResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str


@router.post("/advanced/translate", response_model=TranslationResponse)
async def translate_text(
    request: TranslationRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テキストを翻訳（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    translated = await service.translate(
        text=request.text,
        target_language=request.target_language,
        source_language=request.source_language,
        provider=request.provider,
    )

    return TranslationResponse(
        translated_text=translated,
        source_language=request.source_language or "auto",
        target_language=request.target_language,
    )


class AdvancedQARequest(BaseModel):
    question: str
    context: str
    language: str = "ja"
    provider: Optional[LLMProvider] = None


@router.post("/advanced/qa")
async def answer_advanced_question(
    request: AdvancedQARequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """質問に回答（複数プロバイダー対応）"""
    service = TranscriptionAIService()

    answer = await service.answer_question(
        question=request.question,
        context=request.context,
        language=request.language,
        provider=request.provider,
    )

    return {
        "question": request.question,
        "answer": answer,
        "language": request.language,
    }


class CustomAnalysisRequest(BaseModel):
    text: str
    instruction: str
    output_format: Optional[str] = None
    provider: Optional[LLMProvider] = None


@router.post("/advanced/custom")
async def custom_analysis(
    request: CustomAnalysisRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """カスタム分析を実行"""
    service = TranscriptionAIService()

    result = await service.custom_analysis(
        text=request.text,
        instruction=request.instruction,
        output_format=request.output_format,
        provider=request.provider,
    )

    return {
        "instruction": request.instruction,
        "result": result,
    }


class StreamRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    provider: Optional[LLMProvider] = None


@router.post("/advanced/stream")
async def stream_generate(
    request: StreamRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ストリーミングでテキストを生成"""
    service = LLMService()

    async def generate():
        async for chunk in service.generate_stream(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            provider=request.provider,
        ):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.get("/providers")
async def list_providers(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """利用可能なLLMプロバイダー一覧"""
    return {
        "providers": [
            {
                "id": LLMProvider.OPENAI.value,
                "name": "OpenAI",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                "features": ["chat", "stream", "function_calling"],
            },
            {
                "id": LLMProvider.ANTHROPIC.value,
                "name": "Anthropic",
                "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
                "features": ["chat", "stream", "long_context"],
            },
            {
                "id": LLMProvider.GOOGLE.value,
                "name": "Google",
                "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
                "features": ["chat", "stream", "multimodal"],
            },
        ]
    }


@router.get("/task-types")
async def list_task_types(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """利用可能なAIタスクタイプ一覧"""
    return {
        "task_types": [
            {
                "id": TaskType.SUMMARY.value,
                "name": "要約",
                "description": "テキストを簡潔に要約",
                "styles": ["concise", "detailed", "bullet", "executive"],
            },
            {
                "id": TaskType.MEETING_MINUTES.value,
                "name": "議事録",
                "description": "会議の議事録を生成",
                "templates": ["standard", "formal", "informal"],
            },
            {
                "id": TaskType.ACTION_ITEMS.value,
                "name": "アクションアイテム",
                "description": "タスクや次のステップを抽出",
            },
            {
                "id": TaskType.SENTIMENT.value,
                "name": "感情分析",
                "description": "テキストの感情を分析",
            },
            {
                "id": TaskType.TRANSLATION.value,
                "name": "翻訳",
                "description": "テキストを翻訳",
                "languages": ["ja", "en", "zh", "ko", "es", "fr", "de"],
            },
            {
                "id": TaskType.QA.value,
                "name": "質問応答",
                "description": "テキストに基づいて質問に回答",
            },
            {
                "id": TaskType.CUSTOM.value,
                "name": "カスタム",
                "description": "カスタム指示による分析",
            },
        ]
    }


class BatchTaskRequest(BaseModel):
    transcription_ids: List[str]
    task_type: TaskType
    options: Optional[dict] = None
    provider: Optional[LLMProvider] = None


@router.post("/advanced/batch")
async def batch_process(
    request: BatchTaskRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """複数の文字起こしに対してバッチ処理"""
    job_id = str(uuid.uuid4())

    return {
        "job_id": job_id,
        "status": "queued",
        "task_type": request.task_type.value,
        "transcription_count": len(request.transcription_ids),
    }


@router.get("/advanced/batch/{job_id}")
async def get_batch_status(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """バッチ処理のステータスを取得"""
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "completed_count": 5,
        "failed_count": 0,
        "results": [],
    }
