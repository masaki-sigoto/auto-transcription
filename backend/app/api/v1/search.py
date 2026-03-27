"""検索・ナレッジ管理APIエンドポイント"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.semantic_search_service import (
    SemanticSearchService,
    KnowledgeBaseService,
    SearchResult,
    SimilarMeeting,
    KnowledgeEntry,
)

router = APIRouter(prefix="/search", tags=["search"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    transcription_id: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    answer: str
    sources: List[dict]
    confidence: float


class FAQGenerateRequest(BaseModel):
    transcription_ids: List[str]
    max_questions: int = 10


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セマンティック検索を実行"""
    service = SemanticSearchService(db)

    transcription_uuid = None
    if request.transcription_id:
        try:
            transcription_uuid = uuid.UUID(request.transcription_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    results = await service.search(
        query=request.query,
        user_id=user_id,
        limit=request.limit,
        transcription_id=transcription_uuid,
    )

    return SearchResponse(
        results=results,
        total=len(results),
        query=request.query,
    )


@router.get("/similar/{transcription_id}", response_model=List[SimilarMeeting])
async def find_similar_meetings(
    transcription_id: str,
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """類似会議を検索"""
    try:
        tid = uuid.UUID(transcription_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    service = SemanticSearchService(db)
    results = await service.find_similar_meetings(tid, limit=limit)

    return results


@router.post("/index/{transcription_id}")
async def index_transcription(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしをインデックス化"""
    from sqlalchemy import text

    try:
        tid = uuid.UUID(transcription_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    # 文字起こしを取得
    result = await db.execute(
        text("SELECT title, full_text FROM transcriptions WHERE id = :id"),
        {"id": str(tid)},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Transcription not found")

    title, full_text = row

    # セグメントを取得
    segments_result = await db.execute(
        text("""
            SELECT start_time_ms, end_time_ms, text, speaker_label
            FROM segments
            WHERE transcription_id = :id
            ORDER BY start_time_ms
        """),
        {"id": str(tid)},
    )
    segments = [
        {
            "start_time_ms": s[0],
            "end_time_ms": s[1],
            "text": s[2],
            "speaker_label": s[3],
        }
        for s in segments_result.fetchall()
    ]

    # インデックス化
    service = SemanticSearchService(db)
    await service.index_transcription(tid, title or "無題", segments)

    return {"status": "indexed", "transcription_id": transcription_id}


@router.delete("/index/{transcription_id}")
async def delete_index(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """インデックスを削除"""
    try:
        tid = uuid.UUID(transcription_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    service = SemanticSearchService(db)
    await service.vector_store.delete_by_transcription(tid)

    return {"status": "deleted", "transcription_id": transcription_id}


# ナレッジベース

@router.post("/knowledge/question", response_model=QuestionResponse)
async def ask_question(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ナレッジベースに質問"""
    service = KnowledgeBaseService(db)
    result = await service.answer_question(request.question, user_id)

    return QuestionResponse(
        answer=result["answer"],
        sources=result["sources"],
        confidence=result["confidence"],
    )


@router.post("/knowledge/faq", response_model=List[KnowledgeEntry])
async def generate_faq(
    request: FAQGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """FAQを自動生成"""
    try:
        transcription_uuids = [uuid.UUID(tid) for tid in request.transcription_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transcription_id format")

    service = KnowledgeBaseService(db)
    faqs = await service.generate_faq(
        transcription_uuids,
        max_questions=request.max_questions,
    )

    return faqs


@router.get("/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=2),
    limit: int = Query(5, le=10),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """検索サジェスションを取得"""
    from sqlalchemy import text

    # 最近の検索やタイトルから候補を取得
    result = await db.execute(
        text("""
            SELECT DISTINCT title
            FROM transcriptions
            WHERE title ILIKE :query
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"query": f"%{query}%", "limit": limit},
    )

    suggestions = [row[0] for row in result.fetchall()]

    return {"suggestions": suggestions}
