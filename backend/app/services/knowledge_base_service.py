"""高度な検索・ナレッジベースサービス"""

import os
import uuid
import math
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import hashlib
import json


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    COHERE = "cohere"
    LOCAL = "local"


@dataclass
class SearchResult:
    """検索結果"""
    id: str
    title: str
    content: str
    score: float
    source_type: str  # transcription, meeting, document
    source_id: str
    highlights: List[str]
    metadata: Dict[str, Any]
    created_at: datetime


@dataclass
class VectorDocument:
    """ベクトルドキュメント"""
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]
    source_type: str
    source_id: str
    chunk_index: int
    created_at: datetime


@dataclass
class KnowledgeEntry:
    """ナレッジエントリ"""
    id: str
    title: str
    content: str
    category: str
    tags: List[str]
    source_transcription_ids: List[str]
    embedding: Optional[List[float]]
    created_at: datetime
    updated_at: datetime
    view_count: int = 0
    relevance_score: float = 0.0


@dataclass
class RAGContext:
    """RAGコンテキスト"""
    query: str
    retrieved_documents: List[VectorDocument]
    generated_response: str
    sources: List[Dict[str, Any]]
    confidence_score: float


class EmbeddingService:
    """埋め込みサービス"""

    def __init__(self, provider: EmbeddingProvider = EmbeddingProvider.OPENAI):
        self.provider = provider
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self._embedding_cache: Dict[str, List[float]] = {}

    def _get_cache_key(self, text: str) -> str:
        """キャッシュキーを生成"""
        return hashlib.md5(text.encode()).hexdigest()

    async def generate_embedding(
        self,
        text: str,
        use_cache: bool = True,
    ) -> List[float]:
        """テキストの埋め込みを生成"""
        cache_key = self._get_cache_key(text)

        if use_cache and cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # シミュレーション（実際はOpenAI APIを使用）
        # 1536次元のランダムなベクトルを生成
        import random
        random.seed(hash(text) % (2**32))
        embedding = [random.uniform(-1, 1) for _ in range(1536)]

        # 正規化
        magnitude = math.sqrt(sum(x**2 for x in embedding))
        embedding = [x / magnitude for x in embedding]

        if use_cache:
            self._embedding_cache[cache_key] = embedding

        return embedding

    async def generate_embeddings_batch(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """バッチで埋め込みを生成"""
        tasks = [self.generate_embedding(text) for text in texts]
        return await asyncio.gather(*tasks)

    def cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float],
    ) -> float:
        """コサイン類似度を計算"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a**2 for a in vec1))
        magnitude2 = math.sqrt(sum(b**2 for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)


class VectorStore:
    """ベクトルストア"""

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self._documents: Dict[str, VectorDocument] = {}
        self._indices: Dict[str, List[str]] = {}  # tenant_id -> document_ids

    async def add_document(
        self,
        tenant_id: str,
        content: str,
        metadata: Dict[str, Any],
        source_type: str,
        source_id: str,
        chunk_index: int = 0,
    ) -> VectorDocument:
        """ドキュメントを追加"""
        doc_id = str(uuid.uuid4())
        embedding = await self.embedding_service.generate_embedding(content)

        doc = VectorDocument(
            id=doc_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk_index,
            created_at=datetime.utcnow(),
        )

        self._documents[doc_id] = doc

        if tenant_id not in self._indices:
            self._indices[tenant_id] = []
        self._indices[tenant_id].append(doc_id)

        return doc

    async def add_documents_batch(
        self,
        tenant_id: str,
        documents: List[Dict[str, Any]],
    ) -> List[VectorDocument]:
        """バッチでドキュメントを追加"""
        tasks = [
            self.add_document(
                tenant_id=tenant_id,
                content=doc["content"],
                metadata=doc.get("metadata", {}),
                source_type=doc.get("source_type", "document"),
                source_id=doc.get("source_id", ""),
                chunk_index=doc.get("chunk_index", 0),
            )
            for doc in documents
        ]
        return await asyncio.gather(*tasks)

    async def search(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        filter_source_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Tuple[VectorDocument, float]]:
        """ベクトル検索"""
        query_embedding = await self.embedding_service.generate_embedding(query)

        doc_ids = self._indices.get(tenant_id, [])
        results = []

        for doc_id in doc_ids:
            doc = self._documents.get(doc_id)
            if not doc:
                continue

            if filter_source_type and doc.source_type != filter_source_type:
                continue

            score = self.embedding_service.cosine_similarity(
                query_embedding, doc.embedding
            )

            if score >= min_score:
                results.append((doc, score))

        # スコアでソート
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:top_k]

    async def delete_document(self, doc_id: str) -> bool:
        """ドキュメントを削除"""
        if doc_id in self._documents:
            del self._documents[doc_id]

            for tenant_id, doc_ids in self._indices.items():
                if doc_id in doc_ids:
                    doc_ids.remove(doc_id)

            return True
        return False

    async def delete_by_source(
        self,
        tenant_id: str,
        source_type: str,
        source_id: str,
    ) -> int:
        """ソースでドキュメントを削除"""
        doc_ids = self._indices.get(tenant_id, [])
        deleted = 0

        for doc_id in doc_ids[:]:
            doc = self._documents.get(doc_id)
            if doc and doc.source_type == source_type and doc.source_id == source_id:
                await self.delete_document(doc_id)
                deleted += 1

        return deleted


class TextChunker:
    """テキストチャンカー"""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """テキストをチャンクに分割"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # 文の途中で切らないように調整
            if end < len(text):
                # 最後の句読点を探す
                last_period = max(
                    text.rfind("。", start, end),
                    text.rfind(".", start, end),
                    text.rfind("\n", start, end),
                )
                if last_period > start:
                    end = last_period + 1

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "chunk_index": len(chunks),
                    "start_char": start,
                    "end_char": end,
                    "metadata": metadata or {},
                })

            start = end - self.chunk_overlap

        return chunks

    def chunk_transcription(
        self,
        segments: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """文字起こしセグメントをチャンク"""
        chunks = []
        current_chunk = []
        current_length = 0

        for seg in segments:
            text = seg.get("text", "")
            speaker = seg.get("speaker_id", "")

            segment_text = f"{speaker}: {text}" if speaker else text

            if current_length + len(segment_text) > self.chunk_size and current_chunk:
                # 現在のチャンクを保存
                chunks.append({
                    "content": "\n".join(current_chunk),
                    "chunk_index": len(chunks),
                    "segment_start": segments.index(current_chunk[0]) if current_chunk else 0,
                    "metadata": metadata or {},
                })
                current_chunk = []
                current_length = 0

            current_chunk.append(segment_text)
            current_length += len(segment_text)

        # 最後のチャンク
        if current_chunk:
            chunks.append({
                "content": "\n".join(current_chunk),
                "chunk_index": len(chunks),
                "metadata": metadata or {},
            })

        return chunks


class SemanticSearch:
    """セマンティック検索"""

    def __init__(
        self,
        vector_store: VectorStore,
        chunker: TextChunker,
    ):
        self.vector_store = vector_store
        self.chunker = chunker
        self._keyword_index: Dict[str, Dict[str, List[str]]] = {}  # tenant -> keyword -> doc_ids

    async def index_transcription(
        self,
        tenant_id: str,
        transcription_id: str,
        title: str,
        segments: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """文字起こしをインデックス"""
        meta = metadata or {}
        meta["title"] = title
        meta["transcription_id"] = transcription_id

        chunks = self.chunker.chunk_transcription(segments, meta)

        documents = [
            {
                "content": chunk["content"],
                "metadata": chunk["metadata"],
                "source_type": "transcription",
                "source_id": transcription_id,
                "chunk_index": chunk["chunk_index"],
            }
            for chunk in chunks
        ]

        await self.vector_store.add_documents_batch(tenant_id, documents)

        # キーワードインデックスも更新
        self._update_keyword_index(tenant_id, transcription_id, chunks)

        return len(documents)

    def _update_keyword_index(
        self,
        tenant_id: str,
        doc_id: str,
        chunks: List[Dict[str, Any]],
    ):
        """キーワードインデックスを更新"""
        if tenant_id not in self._keyword_index:
            self._keyword_index[tenant_id] = {}

        for chunk in chunks:
            words = chunk["content"].split()
            for word in words:
                word = word.lower().strip("。、.,'\"")
                if len(word) >= 2:
                    if word not in self._keyword_index[tenant_id]:
                        self._keyword_index[tenant_id][word] = []
                    if doc_id not in self._keyword_index[tenant_id][word]:
                        self._keyword_index[tenant_id][word].append(doc_id)

    async def search(
        self,
        tenant_id: str,
        query: str,
        mode: SearchMode = SearchMode.HYBRID,
        top_k: int = 10,
        filter_source_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """検索を実行"""
        if mode == SearchMode.KEYWORD:
            return await self._keyword_search(tenant_id, query, top_k, filter_source_type)
        elif mode == SearchMode.SEMANTIC:
            return await self._semantic_search(tenant_id, query, top_k, filter_source_type)
        else:
            return await self._hybrid_search(tenant_id, query, top_k, filter_source_type)

    async def _semantic_search(
        self,
        tenant_id: str,
        query: str,
        top_k: int,
        filter_source_type: Optional[str],
    ) -> List[SearchResult]:
        """セマンティック検索"""
        results = await self.vector_store.search(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            filter_source_type=filter_source_type,
        )

        return [
            SearchResult(
                id=doc.id,
                title=doc.metadata.get("title", "無題"),
                content=doc.content,
                score=score,
                source_type=doc.source_type,
                source_id=doc.source_id,
                highlights=self._extract_highlights(doc.content, query),
                metadata=doc.metadata,
                created_at=doc.created_at,
            )
            for doc, score in results
        ]

    async def _keyword_search(
        self,
        tenant_id: str,
        query: str,
        top_k: int,
        filter_source_type: Optional[str],
    ) -> List[SearchResult]:
        """キーワード検索"""
        words = query.lower().split()
        doc_scores: Dict[str, float] = {}

        keyword_index = self._keyword_index.get(tenant_id, {})

        for word in words:
            if word in keyword_index:
                for doc_id in keyword_index[word]:
                    doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1

        # スコアでソート
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, score in sorted_docs[:top_k]:
            doc = self.vector_store._documents.get(doc_id)
            if doc:
                if filter_source_type and doc.source_type != filter_source_type:
                    continue

                results.append(SearchResult(
                    id=doc.id,
                    title=doc.metadata.get("title", "無題"),
                    content=doc.content,
                    score=score / len(words),  # 正規化
                    source_type=doc.source_type,
                    source_id=doc.source_id,
                    highlights=self._extract_highlights(doc.content, query),
                    metadata=doc.metadata,
                    created_at=doc.created_at,
                ))

        return results

    async def _hybrid_search(
        self,
        tenant_id: str,
        query: str,
        top_k: int,
        filter_source_type: Optional[str],
    ) -> List[SearchResult]:
        """ハイブリッド検索"""
        # 両方の検索を実行
        semantic_results = await self._semantic_search(
            tenant_id, query, top_k * 2, filter_source_type
        )
        keyword_results = await self._keyword_search(
            tenant_id, query, top_k * 2, filter_source_type
        )

        # スコアを統合
        combined: Dict[str, SearchResult] = {}

        for result in semantic_results:
            combined[result.id] = result
            combined[result.id].score = result.score * 0.7  # セマンティック重み

        for result in keyword_results:
            if result.id in combined:
                combined[result.id].score += result.score * 0.3  # キーワード重み
            else:
                result.score *= 0.3
                combined[result.id] = result

        # スコアでソート
        sorted_results = sorted(combined.values(), key=lambda x: x.score, reverse=True)

        return sorted_results[:top_k]

    def _extract_highlights(
        self,
        content: str,
        query: str,
        context_chars: int = 100,
    ) -> List[str]:
        """ハイライトを抽出"""
        highlights = []
        words = query.lower().split()
        content_lower = content.lower()

        for word in words:
            idx = content_lower.find(word)
            if idx != -1:
                start = max(0, idx - context_chars)
                end = min(len(content), idx + len(word) + context_chars)
                highlight = content[start:end]

                if start > 0:
                    highlight = "..." + highlight
                if end < len(content):
                    highlight = highlight + "..."

                highlights.append(highlight)

        return highlights[:3]  # 最大3つ


class RAGEngine:
    """RAG（Retrieval-Augmented Generation）エンジン"""

    def __init__(
        self,
        search: SemanticSearch,
    ):
        self.search = search
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    async def generate_response(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 5,
        include_sources: bool = True,
    ) -> RAGContext:
        """RAGで回答を生成"""
        # 関連ドキュメントを検索
        search_results = await self.search.search(
            tenant_id=tenant_id,
            query=query,
            mode=SearchMode.HYBRID,
            top_k=top_k,
        )

        # コンテキストを構築
        context_parts = []
        sources = []

        for result in search_results:
            context_parts.append(result.content)
            sources.append({
                "id": result.source_id,
                "title": result.title,
                "type": result.source_type,
                "score": result.score,
            })

        context = "\n\n---\n\n".join(context_parts)

        # プロンプトを構築
        prompt = f"""以下のコンテキストに基づいて質問に回答してください。

コンテキスト:
{context}

質問: {query}

回答:"""

        # シミュレーション（実際はOpenAI APIを使用）
        generated_response = f"質問「{query}」に対する回答:\n\n"
        generated_response += "検索されたドキュメントに基づくと、"

        if search_results:
            generated_response += f"関連する情報が{len(search_results)}件見つかりました。"
            generated_response += f"\n\n主な内容: {search_results[0].content[:200]}..."
        else:
            generated_response += "関連する情報が見つかりませんでした。"

        # 信頼度スコアを計算
        confidence = sum(r.score for r in search_results) / max(len(search_results), 1)

        # VectorDocumentに変換
        retrieved_docs = []
        for result in search_results:
            doc = self.search.vector_store._documents.get(result.id)
            if doc:
                retrieved_docs.append(doc)

        return RAGContext(
            query=query,
            retrieved_documents=retrieved_docs,
            generated_response=generated_response,
            sources=sources if include_sources else [],
            confidence_score=min(confidence, 1.0),
        )


class KnowledgeBase:
    """ナレッジベース"""

    def __init__(
        self,
        search: SemanticSearch,
        rag: RAGEngine,
    ):
        self.search = search
        self.rag = rag
        self._entries: Dict[str, KnowledgeEntry] = {}
        self._tenant_entries: Dict[str, List[str]] = {}

    async def create_entry(
        self,
        tenant_id: str,
        title: str,
        content: str,
        category: str,
        tags: List[str],
        source_transcription_ids: List[str] = None,
    ) -> KnowledgeEntry:
        """ナレッジエントリを作成"""
        entry_id = str(uuid.uuid4())

        embedding = await self.search.vector_store.embedding_service.generate_embedding(
            f"{title}\n{content}"
        )

        entry = KnowledgeEntry(
            id=entry_id,
            title=title,
            content=content,
            category=category,
            tags=tags,
            source_transcription_ids=source_transcription_ids or [],
            embedding=embedding,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self._entries[entry_id] = entry

        if tenant_id not in self._tenant_entries:
            self._tenant_entries[tenant_id] = []
        self._tenant_entries[tenant_id].append(entry_id)

        return entry

    async def search_entries(
        self,
        tenant_id: str,
        query: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[KnowledgeEntry]:
        """ナレッジエントリを検索"""
        query_embedding = await self.search.vector_store.embedding_service.generate_embedding(query)

        entry_ids = self._tenant_entries.get(tenant_id, [])
        results = []

        for entry_id in entry_ids:
            entry = self._entries.get(entry_id)
            if not entry:
                continue

            if category and entry.category != category:
                continue

            if tags and not any(t in entry.tags for t in tags):
                continue

            score = self.search.vector_store.embedding_service.cosine_similarity(
                query_embedding, entry.embedding
            )
            entry.relevance_score = score
            results.append(entry)

        # スコアでソート
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        return results[:limit]

    async def get_related_transcriptions(
        self,
        tenant_id: str,
        transcription_id: str,
        limit: int = 5,
    ) -> List[SearchResult]:
        """関連する文字起こしを取得"""
        # 現在の文字起こしのコンテンツを取得
        results = await self.search.search(
            tenant_id=tenant_id,
            query="",  # 空クエリ
            mode=SearchMode.SEMANTIC,
            top_k=limit + 1,
            filter_source_type="transcription",
        )

        # 自分自身を除外
        return [r for r in results if r.source_id != transcription_id][:limit]

    async def generate_knowledge_from_transcriptions(
        self,
        tenant_id: str,
        transcription_ids: List[str],
        category: str = "自動生成",
    ) -> List[KnowledgeEntry]:
        """文字起こしからナレッジを自動生成"""
        entries = []

        for transcription_id in transcription_ids:
            # RAGで要約を生成
            context = await self.rag.generate_response(
                tenant_id=tenant_id,
                query=f"transcription_id:{transcription_id}の内容を要約してください",
                top_k=3,
            )

            if context.confidence_score > 0.3:
                entry = await self.create_entry(
                    tenant_id=tenant_id,
                    title=f"自動生成ナレッジ - {transcription_id[:8]}",
                    content=context.generated_response,
                    category=category,
                    tags=["自動生成"],
                    source_transcription_ids=[transcription_id],
                )
                entries.append(entry)

        return entries

    async def get_recommendations(
        self,
        tenant_id: str,
        user_history: List[str],
        limit: int = 5,
    ) -> List[KnowledgeEntry]:
        """ユーザー履歴に基づく推奨"""
        if not user_history:
            return []

        # 履歴を結合してクエリを作成
        combined_query = " ".join(user_history[-5:])  # 最新5件

        return await self.search_entries(
            tenant_id=tenant_id,
            query=combined_query,
            limit=limit,
        )


# グローバルインスタンス
embedding_service = EmbeddingService()
vector_store = VectorStore(embedding_service)
text_chunker = TextChunker()
semantic_search = SemanticSearch(vector_store, text_chunker)
rag_engine = RAGEngine(semantic_search)
knowledge_base = KnowledgeBase(semantic_search, rag_engine)
