"""高度な検索・ナレッジベースAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.knowledge_base_service import (
    semantic_search,
    rag_engine,
    knowledge_base,
    vector_store,
    text_chunker,
    SearchMode,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def get_current_tenant_id() -> str:
    return "default-tenant"


# =====================
# セマンティック検索
# =====================

class SearchRequest(BaseModel):
    query: str
    mode: str = "hybrid"  # keyword, semantic, hybrid
    top_k: int = 10
    source_type: Optional[str] = None


@router.post("/search")
async def search(
    request: SearchRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """セマンティック検索"""
    try:
        mode = SearchMode(request.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}")

    results = await semantic_search.search(
        tenant_id=tenant_id,
        query=request.query,
        mode=mode,
        top_k=request.top_k,
        filter_source_type=request.source_type,
    )

    return {
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "content": r.content[:500] + "..." if len(r.content) > 500 else r.content,
                "score": r.score,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "highlights": r.highlights,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ],
        "count": len(results),
        "mode": request.mode,
    }


@router.get("/search/suggestions")
async def get_search_suggestions(
    query: str,
    limit: int = Query(default=5, le=10),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """検索サジェスト"""
    # 簡易的なサジェスト（実際はより高度な実装が必要）
    results = await semantic_search.search(
        tenant_id=tenant_id,
        query=query,
        mode=SearchMode.KEYWORD,
        top_k=limit,
    )

    suggestions = []
    seen = set()

    for r in results:
        # タイトルからサジェストを抽出
        title = r.title
        if title not in seen:
            suggestions.append(title)
            seen.add(title)

    return {"suggestions": suggestions[:limit]}


# =====================
# インデックス管理
# =====================

class IndexTranscriptionRequest(BaseModel):
    transcription_id: str
    title: str
    segments: List[dict]
    metadata: Optional[dict] = None


@router.post("/index/transcription")
async def index_transcription(
    request: IndexTranscriptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こしをインデックス"""
    count = await semantic_search.index_transcription(
        tenant_id=tenant_id,
        transcription_id=request.transcription_id,
        title=request.title,
        segments=request.segments,
        metadata=request.metadata,
    )

    return {
        "transcription_id": request.transcription_id,
        "chunks_indexed": count,
        "status": "indexed",
    }


class IndexDocumentRequest(BaseModel):
    content: str
    title: str
    source_type: str = "document"
    source_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/index/document")
async def index_document(
    request: IndexDocumentRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ドキュメントをインデックス"""
    source_id = request.source_id or str(uuid.uuid4())

    chunks = text_chunker.chunk_text(
        request.content,
        metadata={"title": request.title, **(request.metadata or {})},
    )

    documents = [
        {
            "content": chunk["content"],
            "metadata": chunk["metadata"],
            "source_type": request.source_type,
            "source_id": source_id,
            "chunk_index": chunk["chunk_index"],
        }
        for chunk in chunks
    ]

    await vector_store.add_documents_batch(tenant_id, documents)

    return {
        "source_id": source_id,
        "chunks_indexed": len(documents),
        "status": "indexed",
    }


@router.delete("/index/{source_type}/{source_id}")
async def delete_from_index(
    source_type: str,
    source_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """インデックスから削除"""
    deleted = await vector_store.delete_by_source(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
    )

    return {
        "source_type": source_type,
        "source_id": source_id,
        "chunks_deleted": deleted,
        "status": "deleted",
    }


# =====================
# RAG
# =====================

class RAGRequest(BaseModel):
    query: str
    top_k: int = 5
    include_sources: bool = True


@router.post("/rag/query")
async def rag_query(
    request: RAGRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """RAGで質問に回答"""
    context = await rag_engine.generate_response(
        tenant_id=tenant_id,
        query=request.query,
        top_k=request.top_k,
        include_sources=request.include_sources,
    )

    return {
        "query": context.query,
        "response": context.generated_response,
        "sources": context.sources,
        "confidence_score": context.confidence_score,
        "documents_retrieved": len(context.retrieved_documents),
    }


@router.post("/rag/summarize")
async def rag_summarize(
    transcription_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """RAGで文字起こしを要約"""
    context = await rag_engine.generate_response(
        tenant_id=tenant_id,
        query=f"以下の文字起こしの主要なポイントを要約してください: {transcription_id}",
        top_k=10,
    )

    return {
        "transcription_id": transcription_id,
        "summary": context.generated_response,
        "confidence_score": context.confidence_score,
    }


# =====================
# ナレッジベース
# =====================

class CreateKnowledgeRequest(BaseModel):
    title: str
    content: str
    category: str
    tags: List[str] = []
    source_transcription_ids: List[str] = []


@router.post("/entries")
async def create_knowledge_entry(
    request: CreateKnowledgeRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ナレッジエントリを作成"""
    entry = await knowledge_base.create_entry(
        tenant_id=tenant_id,
        title=request.title,
        content=request.content,
        category=request.category,
        tags=request.tags,
        source_transcription_ids=request.source_transcription_ids,
    )

    return {
        "id": entry.id,
        "title": entry.title,
        "category": entry.category,
        "tags": entry.tags,
        "created_at": entry.created_at.isoformat(),
    }


class SearchEntriesRequest(BaseModel):
    query: str
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = 10


@router.post("/entries/search")
async def search_knowledge_entries(
    request: SearchEntriesRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ナレッジエントリを検索"""
    entries = await knowledge_base.search_entries(
        tenant_id=tenant_id,
        query=request.query,
        category=request.category,
        tags=request.tags,
        limit=request.limit,
    )

    return {
        "entries": [
            {
                "id": e.id,
                "title": e.title,
                "content": e.content[:300] + "..." if len(e.content) > 300 else e.content,
                "category": e.category,
                "tags": e.tags,
                "relevance_score": e.relevance_score,
                "view_count": e.view_count,
            }
            for e in entries
        ],
        "count": len(entries),
    }


@router.get("/entries/{entry_id}")
async def get_knowledge_entry(
    entry_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ナレッジエントリを取得"""
    entry = knowledge_base._entries.get(entry_id)

    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # ビューカウントを増加
    entry.view_count += 1

    return {
        "id": entry.id,
        "title": entry.title,
        "content": entry.content,
        "category": entry.category,
        "tags": entry.tags,
        "source_transcription_ids": entry.source_transcription_ids,
        "view_count": entry.view_count,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@router.get("/entries/categories")
async def list_categories(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カテゴリ一覧"""
    entry_ids = knowledge_base._tenant_entries.get(tenant_id, [])
    categories = set()

    for entry_id in entry_ids:
        entry = knowledge_base._entries.get(entry_id)
        if entry:
            categories.add(entry.category)

    return {
        "categories": list(categories),
        "count": len(categories),
    }


# =====================
# 関連コンテンツ
# =====================

@router.get("/related/transcriptions/{transcription_id}")
async def get_related_transcriptions(
    transcription_id: str,
    limit: int = Query(default=5, le=20),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """関連する文字起こしを取得"""
    results = await knowledge_base.get_related_transcriptions(
        tenant_id=tenant_id,
        transcription_id=transcription_id,
        limit=limit,
    )

    return {
        "related": [
            {
                "id": r.source_id,
                "title": r.title,
                "score": r.score,
                "source_type": r.source_type,
            }
            for r in results
        ],
        "count": len(results),
    }


class GenerateKnowledgeRequest(BaseModel):
    transcription_ids: List[str]
    category: str = "自動生成"


@router.post("/generate")
async def generate_knowledge(
    request: GenerateKnowledgeRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こしからナレッジを自動生成"""
    entries = await knowledge_base.generate_knowledge_from_transcriptions(
        tenant_id=tenant_id,
        transcription_ids=request.transcription_ids,
        category=request.category,
    )

    return {
        "entries": [
            {
                "id": e.id,
                "title": e.title,
                "category": e.category,
            }
            for e in entries
        ],
        "count": len(entries),
    }


class RecommendationsRequest(BaseModel):
    user_history: List[str]
    limit: int = 5


@router.post("/recommendations")
async def get_recommendations(
    request: RecommendationsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ユーザー向け推奨"""
    entries = await knowledge_base.get_recommendations(
        tenant_id=tenant_id,
        user_history=request.user_history,
        limit=request.limit,
    )

    return {
        "recommendations": [
            {
                "id": e.id,
                "title": e.title,
                "category": e.category,
                "relevance_score": e.relevance_score,
            }
            for e in entries
        ],
        "count": len(entries),
    }


# =====================
# 検索モード情報
# =====================

@router.get("/modes")
async def list_search_modes():
    """検索モード一覧"""
    return {
        "modes": [
            {
                "id": "keyword",
                "name": "キーワード検索",
                "description": "従来のキーワードマッチング検索",
            },
            {
                "id": "semantic",
                "name": "セマンティック検索",
                "description": "意味に基づくベクトル検索",
            },
            {
                "id": "hybrid",
                "name": "ハイブリッド検索",
                "description": "キーワードとセマンティックを組み合わせた検索（推奨）",
            },
        ]
    }
