"""セマンティック検索・ナレッジ管理サービス"""

import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import json
import numpy as np
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import httpx

from app.core.config import get_settings

settings = get_settings()


class SearchResult(BaseModel):
    """検索結果"""
    transcription_id: str
    title: str
    text: str
    score: float
    timestamp_ms: Optional[int]
    speaker: Optional[str]
    highlights: List[str]


class SimilarMeeting(BaseModel):
    """類似会議"""
    transcription_id: str
    title: str
    similarity_score: float
    common_topics: List[str]
    date: str


class KnowledgeEntry(BaseModel):
    """ナレッジエントリ"""
    id: str
    question: str
    answer: str
    source_transcription_ids: List[str]
    confidence: float
    created_at: str


class EmbeddingService:
    """埋め込みベクトル生成サービス"""

    def __init__(self):
        self.openai_api_key = getattr(settings, 'openai_api_key', '')
        self.model = "text-embedding-3-small"
        self.dimension = 1536

    async def generate_embedding(self, text: str) -> List[float]:
        """テキストの埋め込みベクトルを生成"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": self.model,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            return data["data"][0]["embedding"]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """バッチで埋め込みベクトルを生成"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": texts,
                    "model": self.model,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            # インデックス順にソート
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [e["embedding"] for e in embeddings]


class VectorStore:
    """ベクトルストア（Pinecone/pgvector対応）"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService()

    async def create_index(self):
        """pgvector拡張とインデックスを作成"""
        await self.db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transcription_id UUID NOT NULL,
                segment_id UUID,
                text TEXT NOT NULL,
                embedding vector(1536),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS embeddings_vector_idx
            ON embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        await self.db.commit()

    async def upsert_embedding(
        self,
        transcription_id: UUID,
        text: str,
        segment_id: Optional[UUID] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """埋め込みを保存・更新"""
        embedding = await self.embedding_service.generate_embedding(text)

        # IDをハッシュで生成（重複防止）
        content_hash = hashlib.md5(f"{transcription_id}:{text}".encode()).hexdigest()

        await self.db.execute(
            text("""
                INSERT INTO embeddings (id, transcription_id, segment_id, text, embedding, metadata)
                VALUES (:id, :transcription_id, :segment_id, :text, :embedding, :metadata)
                ON CONFLICT (id) DO UPDATE SET
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
            """),
            {
                "id": content_hash,
                "transcription_id": str(transcription_id),
                "segment_id": str(segment_id) if segment_id else None,
                "text": text,
                "embedding": str(embedding),
                "metadata": json.dumps(metadata or {}),
            },
        )
        await self.db.commit()

        return content_hash

    async def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        filter_transcription_id: Optional[UUID] = None,
    ) -> List[Dict]:
        """類似テキストを検索"""
        query_embedding = await self.embedding_service.generate_embedding(query)

        filter_clause = ""
        params = {
            "embedding": str(query_embedding),
            "limit": limit,
            "threshold": threshold,
        }

        if filter_transcription_id:
            filter_clause = "AND transcription_id = :transcription_id"
            params["transcription_id"] = str(filter_transcription_id)

        result = await self.db.execute(
            text(f"""
                SELECT
                    id,
                    transcription_id,
                    segment_id,
                    text,
                    metadata,
                    1 - (embedding <=> :embedding::vector) as similarity
                FROM embeddings
                WHERE 1 - (embedding <=> :embedding::vector) > :threshold
                {filter_clause}
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """),
            params,
        )

        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "transcription_id": row[1],
                "segment_id": row[2],
                "text": row[3],
                "metadata": row[4],
                "similarity": row[5],
            }
            for row in rows
        ]

    async def delete_by_transcription(self, transcription_id: UUID):
        """文字起こしに関連する埋め込みを削除"""
        await self.db.execute(
            text("DELETE FROM embeddings WHERE transcription_id = :id"),
            {"id": str(transcription_id)},
        )
        await self.db.commit()


class SemanticSearchService:
    """セマンティック検索サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.vector_store = VectorStore(db)
        self.embedding_service = EmbeddingService()

    async def index_transcription(
        self,
        transcription_id: UUID,
        title: str,
        segments: List[Dict],
    ):
        """文字起こしをインデックス化"""
        # タイトルをインデックス
        await self.vector_store.upsert_embedding(
            transcription_id=transcription_id,
            text=title,
            metadata={"type": "title"},
        )

        # セグメントをチャンク化してインデックス
        chunk_size = 500  # 文字数
        current_chunk = []
        current_length = 0
        chunk_start_ms = 0

        for segment in segments:
            text = segment.get("text", "")
            start_ms = segment.get("start_time_ms", 0)
            speaker = segment.get("speaker_label")

            if current_length == 0:
                chunk_start_ms = start_ms

            current_chunk.append(text)
            current_length += len(text)

            if current_length >= chunk_size:
                chunk_text = " ".join(current_chunk)
                await self.vector_store.upsert_embedding(
                    transcription_id=transcription_id,
                    text=chunk_text,
                    metadata={
                        "type": "segment_chunk",
                        "start_time_ms": chunk_start_ms,
                        "speaker": speaker,
                    },
                )
                current_chunk = []
                current_length = 0

        # 残りをインデックス
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            await self.vector_store.upsert_embedding(
                transcription_id=transcription_id,
                text=chunk_text,
                metadata={
                    "type": "segment_chunk",
                    "start_time_ms": chunk_start_ms,
                },
            )

    async def search(
        self,
        query: str,
        user_id: UUID,
        limit: int = 20,
        transcription_id: Optional[UUID] = None,
    ) -> List[SearchResult]:
        """セマンティック検索を実行"""
        results = await self.vector_store.search_similar(
            query=query,
            limit=limit,
            filter_transcription_id=transcription_id,
        )

        search_results = []
        for r in results:
            # 文字起こしタイトルを取得
            title = await self._get_transcription_title(r["transcription_id"])

            # ハイライト生成
            highlights = self._generate_highlights(r["text"], query)

            metadata = r.get("metadata") or {}

            search_results.append(SearchResult(
                transcription_id=r["transcription_id"],
                title=title,
                text=r["text"],
                score=r["similarity"],
                timestamp_ms=metadata.get("start_time_ms"),
                speaker=metadata.get("speaker"),
                highlights=highlights,
            ))

        return search_results

    async def _get_transcription_title(self, transcription_id: str) -> str:
        """文字起こしタイトルを取得"""
        result = await self.db.execute(
            text("SELECT title FROM transcriptions WHERE id = :id"),
            {"id": transcription_id},
        )
        row = result.fetchone()
        return row[0] if row else "無題"

    def _generate_highlights(self, text: str, query: str) -> List[str]:
        """検索クエリに基づくハイライトを生成"""
        # シンプルな実装：クエリに関連する部分を抽出
        words = query.lower().split()
        sentences = text.split("。")

        highlights = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(word in sentence_lower for word in words):
                highlights.append(sentence.strip())
                if len(highlights) >= 3:
                    break

        return highlights if highlights else [text[:200]]

    async def find_similar_meetings(
        self,
        transcription_id: UUID,
        limit: int = 5,
    ) -> List[SimilarMeeting]:
        """類似会議を検索"""
        # 対象文字起こしの埋め込みを取得
        result = await self.db.execute(
            text("""
                SELECT text, embedding
                FROM embeddings
                WHERE transcription_id = :id AND metadata->>'type' = 'title'
                LIMIT 1
            """),
            {"id": str(transcription_id)},
        )
        row = result.fetchone()

        if not row:
            return []

        # 類似文字起こしを検索
        similar = await self.vector_store.search_similar(
            query=row[0],
            limit=limit + 1,  # 自分自身を除く
        )

        meetings = []
        for s in similar:
            if s["transcription_id"] == str(transcription_id):
                continue

            title = await self._get_transcription_title(s["transcription_id"])

            # 共通トピックを抽出（簡易版）
            common_topics = await self._extract_common_topics(
                transcription_id,
                UUID(s["transcription_id"]),
            )

            meetings.append(SimilarMeeting(
                transcription_id=s["transcription_id"],
                title=title,
                similarity_score=s["similarity"],
                common_topics=common_topics,
                date="",  # 実際はDBから取得
            ))

            if len(meetings) >= limit:
                break

        return meetings

    async def _extract_common_topics(
        self,
        transcription_id1: UUID,
        transcription_id2: UUID,
    ) -> List[str]:
        """共通トピックを抽出"""
        # 実際の実装ではキーワード抽出を使用
        return ["プロジェクト", "進捗", "課題"]


class KnowledgeBaseService:
    """ナレッジベースサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.search_service = SemanticSearchService(db)

    async def generate_faq(
        self,
        transcription_ids: List[UUID],
        max_questions: int = 10,
    ) -> List[KnowledgeEntry]:
        """文字起こしからFAQを自動生成"""
        # 文字起こしテキストを取得
        texts = []
        for tid in transcription_ids:
            result = await self.db.execute(
                text("SELECT full_text FROM transcriptions WHERE id = :id"),
                {"id": str(tid)},
            )
            row = result.fetchone()
            if row and row[0]:
                texts.append(row[0])

        if not texts:
            return []

        combined_text = "\n\n".join(texts)

        # GPT-4でFAQ生成
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {getattr(settings, 'openai_api_key', '')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": """与えられた会議記録からFAQを生成してください。
各FAQには質問と回答を含めてください。
JSON配列形式で出力してください。
例: [{"question": "質問", "answer": "回答"}]""",
                        },
                        {
                            "role": "user",
                            "content": f"以下の会議記録からFAQを{max_questions}個生成してください:\n\n{combined_text[:8000]}",
                        },
                    ],
                    "max_tokens": 2000,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        try:
            faqs = json.loads(data["choices"][0]["message"]["content"])
        except json.JSONDecodeError:
            return []

        entries = []
        for i, faq in enumerate(faqs):
            entry = KnowledgeEntry(
                id=f"faq_{i}",
                question=faq.get("question", ""),
                answer=faq.get("answer", ""),
                source_transcription_ids=[str(tid) for tid in transcription_ids],
                confidence=0.8,
                created_at=datetime.utcnow().isoformat(),
            )
            entries.append(entry)

        return entries

    async def answer_question(
        self,
        question: str,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """ナレッジベースから質問に回答"""
        # 関連する文字起こしを検索
        search_results = await self.search_service.search(
            query=question,
            user_id=user_id,
            limit=5,
        )

        if not search_results:
            return {
                "answer": "関連する情報が見つかりませんでした。",
                "sources": [],
                "confidence": 0.0,
            }

        # コンテキストを構築
        context = "\n\n".join([
            f"出典: {r.title}\n{r.text}"
            for r in search_results
        ])

        # GPT-4で回答生成
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {getattr(settings, 'openai_api_key', '')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": """会議記録に基づいて質問に回答してください。
回答は簡潔で正確にしてください。
情報がない場合は「情報がありません」と回答してください。""",
                        },
                        {
                            "role": "user",
                            "content": f"コンテキスト:\n{context}\n\n質問: {question}",
                        },
                    ],
                    "max_tokens": 500,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        answer = data["choices"][0]["message"]["content"]

        return {
            "answer": answer,
            "sources": [
                {
                    "transcription_id": r.transcription_id,
                    "title": r.title,
                    "relevance": r.score,
                }
                for r in search_results[:3]
            ],
            "confidence": max(r.score for r in search_results),
        }
