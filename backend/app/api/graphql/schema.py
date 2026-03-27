"""GraphQL スキーマ定義"""

import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import uuid


# === Types ===

@strawberry.type
class User:
    id: strawberry.ID
    email: str
    name: Optional[str]
    created_at: datetime


@strawberry.type
class Speaker:
    id: strawberry.ID
    label: str
    name: Optional[str]


@strawberry.type
class Segment:
    id: strawberry.ID
    start_time_ms: int
    end_time_ms: int
    text: str
    speaker: Optional[Speaker]
    confidence: Optional[float]


@strawberry.type
class Transcription:
    id: strawberry.ID
    title: Optional[str]
    status: str
    audio_duration_sec: Optional[int]
    language: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    full_text: Optional[str]
    summary: Optional[str]
    segments: List[Segment]
    speakers: List[Speaker]


@strawberry.type
class Team:
    id: strawberry.ID
    name: str
    description: Optional[str]
    created_at: datetime
    member_count: int


@strawberry.type
class AnalysisResult:
    id: strawberry.ID
    transcription_id: strawberry.ID
    analysis_type: str
    result: str
    created_at: datetime


@strawberry.type
class SearchResult:
    transcription_id: strawberry.ID
    title: str
    text: str
    score: float
    timestamp_ms: Optional[int]


@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]


@strawberry.type
class TranscriptionEdge:
    node: Transcription
    cursor: str


@strawberry.type
class TranscriptionConnection:
    edges: List[TranscriptionEdge]
    page_info: PageInfo
    total_count: int


# === Input Types ===

@strawberry.input
class TranscriptionFilter:
    status: Optional[str] = None
    language: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    search: Optional[str] = None


@strawberry.input
class CreateTranscriptionInput:
    title: Optional[str] = None
    language: str = "ja"


@strawberry.input
class UpdateTranscriptionInput:
    title: Optional[str] = None
    status: Optional[str] = None


@strawberry.input
class UpdateSegmentInput:
    text: str
    speaker_id: Optional[strawberry.ID] = None


# === Queries ===

@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info) -> Optional[User]:
        """現在のユーザーを取得"""
        # 実際の実装ではコンテキストからユーザーを取得
        return User(
            id=strawberry.ID("00000000-0000-0000-0000-000000000001"),
            email="test@example.com",
            name="Test User",
            created_at=datetime.utcnow(),
        )

    @strawberry.field
    async def transcription(
        self,
        info,
        id: strawberry.ID,
    ) -> Optional[Transcription]:
        """文字起こしを取得"""
        # 実際の実装ではDBから取得
        return Transcription(
            id=id,
            title="サンプル会議",
            status="completed",
            audio_duration_sec=3600,
            language="ja",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            full_text="これはサンプルテキストです。",
            summary="サンプル会議の要約です。",
            segments=[
                Segment(
                    id=strawberry.ID("seg-1"),
                    start_time_ms=0,
                    end_time_ms=5000,
                    text="これはサンプルテキストです。",
                    speaker=Speaker(id=strawberry.ID("spk-1"), label="話者1", name="田中"),
                    confidence=0.95,
                )
            ],
            speakers=[
                Speaker(id=strawberry.ID("spk-1"), label="話者1", name="田中"),
            ],
        )

    @strawberry.field
    async def transcriptions(
        self,
        info,
        filter: Optional[TranscriptionFilter] = None,
        first: Optional[int] = 10,
        after: Optional[str] = None,
    ) -> TranscriptionConnection:
        """文字起こし一覧を取得（ページネーション対応）"""
        # 実際の実装ではDBから取得
        sample = Transcription(
            id=strawberry.ID("00000000-0000-0000-0000-000000000001"),
            title="サンプル会議",
            status="completed",
            audio_duration_sec=3600,
            language="ja",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            full_text="これはサンプルテキストです。",
            summary="サンプル会議の要約です。",
            segments=[],
            speakers=[],
        )

        return TranscriptionConnection(
            edges=[TranscriptionEdge(node=sample, cursor="cursor-1")],
            page_info=PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor="cursor-1",
                end_cursor="cursor-1",
            ),
            total_count=1,
        )

    @strawberry.field
    async def search(
        self,
        info,
        query: str,
        limit: int = 20,
    ) -> List[SearchResult]:
        """セマンティック検索"""
        # 実際の実装では検索サービスを使用
        return [
            SearchResult(
                transcription_id=strawberry.ID("00000000-0000-0000-0000-000000000001"),
                title="サンプル会議",
                text="検索にマッチしたテキスト",
                score=0.95,
                timestamp_ms=5000,
            )
        ]

    @strawberry.field
    async def teams(self, info) -> List[Team]:
        """チーム一覧を取得"""
        return [
            Team(
                id=strawberry.ID("team-1"),
                name="開発チーム",
                description="開発チームの説明",
                created_at=datetime.utcnow(),
                member_count=5,
            )
        ]


# === Mutations ===

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_transcription(
        self,
        info,
        input: CreateTranscriptionInput,
    ) -> Transcription:
        """文字起こしを作成"""
        new_id = str(uuid.uuid4())

        return Transcription(
            id=strawberry.ID(new_id),
            title=input.title,
            status="pending",
            audio_duration_sec=None,
            language=input.language,
            created_at=datetime.utcnow(),
            updated_at=None,
            full_text=None,
            summary=None,
            segments=[],
            speakers=[],
        )

    @strawberry.mutation
    async def update_transcription(
        self,
        info,
        id: strawberry.ID,
        input: UpdateTranscriptionInput,
    ) -> Transcription:
        """文字起こしを更新"""
        return Transcription(
            id=id,
            title=input.title,
            status=input.status or "completed",
            audio_duration_sec=3600,
            language="ja",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            full_text="更新されたテキスト",
            summary=None,
            segments=[],
            speakers=[],
        )

    @strawberry.mutation
    async def delete_transcription(
        self,
        info,
        id: strawberry.ID,
    ) -> bool:
        """文字起こしを削除"""
        # 実際の実装ではDBから削除
        return True

    @strawberry.mutation
    async def update_segment(
        self,
        info,
        transcription_id: strawberry.ID,
        segment_id: strawberry.ID,
        input: UpdateSegmentInput,
    ) -> Segment:
        """セグメントを更新"""
        return Segment(
            id=segment_id,
            start_time_ms=0,
            end_time_ms=5000,
            text=input.text,
            speaker=None,
            confidence=1.0,
        )

    @strawberry.mutation
    async def generate_summary(
        self,
        info,
        transcription_id: strawberry.ID,
    ) -> AnalysisResult:
        """要約を生成"""
        return AnalysisResult(
            id=strawberry.ID(str(uuid.uuid4())),
            transcription_id=transcription_id,
            analysis_type="summary",
            result="AI生成された要約です。",
            created_at=datetime.utcnow(),
        )

    @strawberry.mutation
    async def generate_meeting_minutes(
        self,
        info,
        transcription_id: strawberry.ID,
    ) -> AnalysisResult:
        """議事録を生成"""
        return AnalysisResult(
            id=strawberry.ID(str(uuid.uuid4())),
            transcription_id=transcription_id,
            analysis_type="meeting_minutes",
            result='{"agenda": [], "decisions": [], "action_items": []}',
            created_at=datetime.utcnow(),
        )


# === Subscriptions ===

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def transcription_updated(
        self,
        info,
        transcription_id: strawberry.ID,
    ) -> Transcription:
        """文字起こし更新をサブスクライブ"""
        import asyncio

        # 実際の実装ではRedis Pub/Subを使用
        while True:
            await asyncio.sleep(1)
            yield Transcription(
                id=transcription_id,
                title="リアルタイム更新",
                status="processing",
                audio_duration_sec=None,
                language="ja",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                full_text="リアルタイムで更新されるテキスト",
                summary=None,
                segments=[],
                speakers=[],
            )

    @strawberry.subscription
    async def realtime_transcription(
        self,
        info,
        session_id: str,
    ) -> Segment:
        """リアルタイム文字起こしをサブスクライブ"""
        import asyncio

        # 実際の実装ではWebSocket/Redis Pub/Subを使用
        segment_id = 0
        while True:
            await asyncio.sleep(2)
            segment_id += 1
            yield Segment(
                id=strawberry.ID(f"realtime-{segment_id}"),
                start_time_ms=segment_id * 2000,
                end_time_ms=(segment_id + 1) * 2000,
                text=f"リアルタイムセグメント {segment_id}",
                speaker=Speaker(id=strawberry.ID("spk-1"), label="話者1", name=None),
                confidence=0.9,
            )


# スキーマを作成
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)

# GraphQLルーターを作成
graphql_router = GraphQLRouter(schema)
