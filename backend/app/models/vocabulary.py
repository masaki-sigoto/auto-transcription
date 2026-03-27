import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class VocabularyDictionary(Base):
    """語彙辞書モデル"""
    __tablename__ = "vocabulary_dictionaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    language = Column(String(10), default="ja")  # ja, en, etc.
    is_active = Column(Boolean, default=True)
    is_shared = Column(Boolean, default=False)  # チーム内で共有

    # 統計
    word_count = Column(Integer, default=0)
    usage_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    user = relationship("User")
    team = relationship("Team")
    words = relationship("VocabularyWord", back_populates="dictionary", cascade="all, delete-orphan")


class VocabularyWord(Base):
    """語彙ワードモデル"""
    __tablename__ = "vocabulary_words"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dictionary_id = Column(UUID(as_uuid=True), ForeignKey("vocabulary_dictionaries.id", ondelete="CASCADE"), nullable=False)

    # メインワード
    word = Column(String(255), nullable=False)
    reading = Column(String(255), nullable=True)  # よみがな
    pronunciation = Column(String(255), nullable=True)  # 発音表記

    # 表記揺れ・別名
    aliases = Column(JSON, default=list)  # ["表記1", "表記2", ...]

    # カテゴリ・タグ
    category = Column(String(100), nullable=True)  # 人名、地名、専門用語など
    tags = Column(JSON, default=list)

    # 優先度・重み
    priority = Column(Integer, default=0)  # 高いほど優先
    boost_factor = Column(String(10), default="1.0")  # 認識スコアのブースト係数

    # メタデータ
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    dictionary = relationship("VocabularyDictionary", back_populates="words")


class TranscriptionVocabulary(Base):
    """文字起こし-辞書関連モデル"""
    __tablename__ = "transcription_vocabularies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcription_id = Column(UUID(as_uuid=True), ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)
    dictionary_id = Column(UUID(as_uuid=True), ForeignKey("vocabulary_dictionaries.id", ondelete="CASCADE"), nullable=False)

    # 使用統計
    words_matched = Column(Integer, default=0)
    corrections_applied = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    transcription = relationship("Transcription")
    dictionary = relationship("VocabularyDictionary")


class AutoCorrectionRule(Base):
    """自動修正ルールモデル"""
    __tablename__ = "auto_correction_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    is_shared = Column(Boolean, default=False)

    # ルールタイプ
    rule_type = Column(String(50), nullable=False)  # replace, regex, fuzzy

    # パターン
    pattern = Column(String(500), nullable=False)  # 検索パターン
    replacement = Column(String(500), nullable=False)  # 置換先
    case_sensitive = Column(Boolean, default=False)

    # 適用条件
    apply_to_speaker = Column(String(255), nullable=True)  # 特定話者のみ
    apply_to_category = Column(String(100), nullable=True)  # 特定カテゴリのみ

    # 統計
    usage_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    user = relationship("User")
    team = relationship("Team")
