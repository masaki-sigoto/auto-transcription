import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, JSON, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class UsageMetrics(Base):
    """使用量メトリクスモデル（日次集計）"""
    __tablename__ = "usage_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)

    # 文字起こし統計
    transcriptions_count = Column(Integer, default=0)
    total_audio_duration_sec = Column(Integer, default=0)
    total_characters = Column(Integer, default=0)
    total_words = Column(Integer, default=0)

    # API使用量
    api_calls_count = Column(Integer, default=0)
    ai_tokens_used = Column(Integer, default=0)

    # ストレージ使用量
    storage_used_bytes = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    user = relationship("User")

    class Config:
        # 複合ユニークキー
        __table_args__ = (
            {'extend_existing': True},
        )


class TranscriptionAnalytics(Base):
    """文字起こし分析モデル"""
    __tablename__ = "transcription_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcription_id = Column(UUID(as_uuid=True), ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False, unique=True)

    # 基本統計
    total_duration_sec = Column(Integer, default=0)
    total_segments = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    total_characters = Column(Integer, default=0)
    unique_words = Column(Integer, default=0)

    # 話者統計
    speaker_count = Column(Integer, default=0)
    speaker_stats = Column(JSON, default=dict)  # {speaker_id: {duration, word_count, ...}}

    # 言語統計
    language = Column(String(10), nullable=True)
    language_confidence = Column(Float, nullable=True)

    # 感情・トーン分析
    sentiment_scores = Column(JSON, default=dict)  # {positive, negative, neutral}
    emotion_distribution = Column(JSON, default=dict)  # {joy, anger, sadness, ...}

    # トピック分析
    topics = Column(JSON, default=list)  # [{topic, score, keywords}]
    keywords = Column(JSON, default=list)  # [{word, count, tfidf}]

    # 発話パターン
    speaking_rate_wpm = Column(Float, nullable=True)  # 1分あたりの単語数
    pause_count = Column(Integer, default=0)
    avg_pause_duration_ms = Column(Integer, nullable=True)
    filler_word_count = Column(Integer, default=0)  # えーと、あのーなど

    # 品質スコア
    overall_confidence = Column(Float, nullable=True)
    clarity_score = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    transcription = relationship("Transcription")


class Report(Base):
    """レポートモデル"""
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    report_type = Column(String(50), nullable=False)  # usage, transcription, speaker, custom

    # レポート設定
    config = Column(JSON, default=dict)  # フィルター、期間、グループ化など
    schedule = Column(JSON, nullable=True)  # 定期実行設定

    # 最終実行
    last_run_at = Column(DateTime, nullable=True)
    last_result = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    user = relationship("User")
    team = relationship("Team")
