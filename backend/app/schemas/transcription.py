from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class TranscriptionOptions(BaseModel):
    enable_diarization: bool = True
    enable_llm_correction: bool = True
    remove_filler_words: bool = True
    custom_vocabulary: list[str] = Field(default_factory=list)


class TranscriptionCreate(BaseModel):
    audio_url: str
    title: str | None = None
    language: str = "ja"
    engine: str = "reazon"  # reazon, whisper, hybrid
    options: TranscriptionOptions = Field(default_factory=TranscriptionOptions)


class TranscriptionUpdate(BaseModel):
    title: str | None = None


class SpeakerResponse(BaseModel):
    id: UUID
    label: str
    color: str | None

    class Config:
        from_attributes = True


class SegmentResponse(BaseModel):
    id: UUID
    start_time_ms: int
    end_time_ms: int
    text: str
    speaker_id: UUID | None
    confidence: float | None
    is_edited: bool

    class Config:
        from_attributes = True


class SegmentUpdate(BaseModel):
    text: str | None = None
    speaker_id: UUID | None = None


class TranscriptionResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None
    status: str
    audio_url: str
    audio_duration_sec: int | None
    language: str
    engine: str
    enable_diarization: bool
    enable_llm_correction: bool
    summary: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TranscriptionDetailResponse(TranscriptionResponse):
    segments: list[SegmentResponse]
    speakers: list[SpeakerResponse]


class TranscriptionListResponse(BaseModel):
    items: list[TranscriptionResponse]
    total: int
    page: int
    per_page: int


class TranscriptionJobResponse(BaseModel):
    id: UUID
    status: str
    estimated_completion_sec: int | None


class ExportRequest(BaseModel):
    format: str = "txt"  # txt, srt, vtt, docx, json


class ExportResponse(BaseModel):
    download_url: str
    expires_at: datetime
