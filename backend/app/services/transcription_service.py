import uuid
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.transcription import Transcription, Segment, Speaker
from app.schemas.transcription import (
    TranscriptionCreate,
    TranscriptionUpdate,
    SegmentUpdate,
)


class TranscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: uuid.UUID, data: TranscriptionCreate) -> Transcription:
        transcription = Transcription(
            user_id=user_id,
            title=data.title,
            audio_url=data.audio_url,
            language=data.language,
            engine=data.engine,
            enable_diarization=data.options.enable_diarization,
            enable_llm_correction=data.options.enable_llm_correction,
            status="pending",
        )
        self.db.add(transcription)
        await self.db.flush()
        await self.db.refresh(transcription)
        return transcription

    async def get_by_id(
        self, transcription_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> Transcription | None:
        query = (
            select(Transcription)
            .options(selectinload(Transcription.segments), selectinload(Transcription.speakers))
            .where(Transcription.id == transcription_id)
        )
        if user_id:
            query = query.where(Transcription.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: uuid.UUID, page: int = 1, per_page: int = 20
    ) -> tuple[list[Transcription], int]:
        # Count query
        count_query = select(func.count()).where(Transcription.user_id == user_id)
        total = await self.db.execute(count_query)
        total_count = total.scalar_one()

        # Data query
        offset = (page - 1) * per_page
        query = (
            select(Transcription)
            .where(Transcription.user_id == user_id)
            .order_by(Transcription.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        transcriptions = result.scalars().all()

        return list(transcriptions), total_count

    async def update(
        self, transcription_id: uuid.UUID, user_id: uuid.UUID, data: TranscriptionUpdate
    ) -> Transcription | None:
        transcription = await self.get_by_id(transcription_id, user_id)
        if not transcription:
            return None

        if data.title is not None:
            transcription.title = data.title

        transcription.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(transcription)
        return transcription

    async def delete(self, transcription_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        transcription = await self.get_by_id(transcription_id, user_id)
        if not transcription:
            return False

        await self.db.delete(transcription)
        return True

    async def update_status(
        self, transcription_id: uuid.UUID, status: str, error_message: str | None = None
    ) -> Transcription | None:
        query = select(Transcription).where(Transcription.id == transcription_id)
        result = await self.db.execute(query)
        transcription = result.scalar_one_or_none()

        if not transcription:
            return None

        transcription.status = status
        if error_message:
            transcription.error_message = error_message
        transcription.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(transcription)
        return transcription

    async def add_segments(
        self, transcription_id: uuid.UUID, segments_data: list[dict]
    ) -> list[Segment]:
        segments = []
        for seg_data in segments_data:
            segment = Segment(
                transcription_id=transcription_id,
                start_time_ms=seg_data["start_time_ms"],
                end_time_ms=seg_data["end_time_ms"],
                text=seg_data["text"],
                speaker_id=seg_data.get("speaker_id"),
                confidence=seg_data.get("confidence"),
            )
            self.db.add(segment)
            segments.append(segment)

        await self.db.flush()
        return segments

    async def update_segment(
        self, segment_id: uuid.UUID, data: SegmentUpdate
    ) -> Segment | None:
        query = select(Segment).where(Segment.id == segment_id)
        result = await self.db.execute(query)
        segment = result.scalar_one_or_none()

        if not segment:
            return None

        if data.text is not None:
            segment.text = data.text
            segment.is_edited = True
        if data.speaker_id is not None:
            segment.speaker_id = data.speaker_id

        await self.db.flush()
        await self.db.refresh(segment)
        return segment

    async def create_speakers(
        self, transcription_id: uuid.UUID, speaker_labels: list[str]
    ) -> list[Speaker]:
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]
        speakers = []

        for i, label in enumerate(speaker_labels):
            speaker = Speaker(
                transcription_id=transcription_id,
                label=label,
                color=colors[i % len(colors)],
            )
            self.db.add(speaker)
            speakers.append(speaker)

        await self.db.flush()
        return speakers
