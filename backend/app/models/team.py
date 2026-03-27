import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class TeamRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class SharePermission(str, enum.Enum):
    VIEW = "view"
    COMMENT = "comment"
    EDIT = "edit"


class Team(Base):
    """チームモデル"""
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    shared_transcriptions = relationship("TranscriptionShare", back_populates="team")


class TeamMember(Base):
    """チームメンバーモデル"""
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(TeamRole), default=TeamRole.MEMBER)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    team = relationship("Team", back_populates="members")
    user = relationship("User")


class TeamInvitation(Base):
    """チーム招待モデル"""
    __tablename__ = "team_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(Enum(TeamRole), default=TeamRole.MEMBER)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    team = relationship("Team")
    inviter = relationship("User")


class TranscriptionShare(Base):
    """文字起こし共有モデル"""
    __tablename__ = "transcription_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcription_id = Column(UUID(as_uuid=True), ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)

    # チームまたはユーザーに共有
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    permission = Column(Enum(SharePermission), default=SharePermission.VIEW)
    shared_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    transcription = relationship("Transcription")
    team = relationship("Team", back_populates="shared_transcriptions")
    shared_with_user = relationship("User", foreign_keys=[user_id])
    sharer = relationship("User", foreign_keys=[shared_by])


class TranscriptionComment(Base):
    """文字起こしコメントモデル"""
    __tablename__ = "transcription_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcription_id = Column(UUID(as_uuid=True), ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=True)

    content = Column(Text, nullable=False)
    timestamp_ms = Column(String(50), nullable=True)  # タイムスタンプへの参照
    parent_id = Column(UUID(as_uuid=True), ForeignKey("transcription_comments.id"), nullable=True)

    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # リレーション
    transcription = relationship("Transcription")
    user = relationship("User")
    segment = relationship("Segment")
    replies = relationship("TranscriptionComment", remote_side=[id])
