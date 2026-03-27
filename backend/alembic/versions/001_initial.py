"""initial migration

Revision ID: 001
Revises:
Create Date: 2024-12-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('plan', sa.String(20), server_default='free'),
        sa.Column('usage_minutes_month', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Transcriptions table
    op.create_table(
        'transcriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('audio_url', sa.Text(), nullable=False),
        sa.Column('audio_duration_sec', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(10), server_default='ja'),
        sa.Column('engine', sa.String(50), server_default='reazon'),
        sa.Column('enable_diarization', sa.Boolean(), server_default='true'),
        sa.Column('enable_llm_correction', sa.Boolean(), server_default='true'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_transcriptions_user', 'transcriptions', ['user_id'])
    op.create_index('idx_transcriptions_status', 'transcriptions', ['status'])

    # Speakers table
    op.create_table(
        'speakers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transcription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transcriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(50), nullable=False),
        sa.Column('color', sa.String(20), nullable=True),
    )

    # Segments table
    op.create_table(
        'segments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transcription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transcriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('speaker_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('speakers.id'), nullable=True),
        sa.Column('start_time_ms', sa.Integer(), nullable=False),
        sa.Column('end_time_ms', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('is_edited', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_segments_trans', 'segments', ['transcription_id'])
    op.create_index('idx_segments_time', 'segments', ['start_time_ms'])


def downgrade() -> None:
    op.drop_table('segments')
    op.drop_table('speakers')
    op.drop_table('transcriptions')
    op.drop_table('users')
