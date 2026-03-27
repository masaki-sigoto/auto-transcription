import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.team import (
    Team,
    TeamMember,
    TeamInvitation,
    TranscriptionShare,
    TranscriptionComment,
    TeamRole,
    SharePermission,
)
from app.models.user import User


class TeamService:
    """チーム管理サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # チーム管理
    # =========================================================================

    async def create_team(
        self,
        name: str,
        owner_id: uuid.UUID,
        description: Optional[str] = None,
    ) -> Team:
        """チームを作成"""
        team = Team(
            name=name,
            description=description,
        )
        self.db.add(team)
        await self.db.flush()

        # オーナーをメンバーとして追加
        member = TeamMember(
            team_id=team.id,
            user_id=owner_id,
            role=TeamRole.OWNER,
        )
        self.db.add(member)
        await self.db.commit()

        return team

    async def get_team(self, team_id: uuid.UUID) -> Optional[Team]:
        """チームを取得"""
        query = (
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.members))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_user_teams(self, user_id: uuid.UUID) -> list[Team]:
        """ユーザーが所属するチーム一覧を取得"""
        query = (
            select(Team)
            .join(TeamMember)
            .where(TeamMember.user_id == user_id)
            .options(selectinload(Team.members))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_team(
        self,
        team_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Team]:
        """チームを更新"""
        team = await self.get_team(team_id)
        if not team:
            return None

        if name:
            team.name = name
        if description is not None:
            team.description = description

        await self.db.commit()
        return team

    async def delete_team(self, team_id: uuid.UUID) -> bool:
        """チームを削除"""
        team = await self.get_team(team_id)
        if not team:
            return False

        await self.db.delete(team)
        await self.db.commit()
        return True

    # =========================================================================
    # メンバー管理
    # =========================================================================

    async def get_member_role(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[TeamRole]:
        """ユーザーのチーム内ロールを取得"""
        query = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()
        return member.role if member else None

    async def add_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: TeamRole = TeamRole.MEMBER,
    ) -> TeamMember:
        """メンバーを追加"""
        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            role=role,
        )
        self.db.add(member)
        await self.db.commit()
        return member

    async def update_member_role(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: TeamRole,
    ) -> Optional[TeamMember]:
        """メンバーのロールを更新"""
        query = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()

        if not member:
            return None

        member.role = role
        await self.db.commit()
        return member

    async def remove_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """メンバーを削除"""
        query = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()

        if not member:
            return False

        await self.db.delete(member)
        await self.db.commit()
        return True

    async def list_team_members(self, team_id: uuid.UUID) -> list[TeamMember]:
        """チームメンバー一覧を取得"""
        query = (
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .options(selectinload(TeamMember.user))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # 招待管理
    # =========================================================================

    async def create_invitation(
        self,
        team_id: uuid.UUID,
        email: str,
        invited_by: uuid.UUID,
        role: TeamRole = TeamRole.MEMBER,
        expires_days: int = 7,
    ) -> TeamInvitation:
        """招待を作成"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

        invitation = TeamInvitation(
            team_id=team_id,
            email=email,
            role=role,
            invited_by=invited_by,
            token=token,
            expires_at=expires_at,
        )
        self.db.add(invitation)
        await self.db.commit()
        return invitation

    async def get_invitation_by_token(self, token: str) -> Optional[TeamInvitation]:
        """トークンで招待を取得"""
        query = (
            select(TeamInvitation)
            .where(
                TeamInvitation.token == token,
                TeamInvitation.accepted_at.is_(None),
                TeamInvitation.expires_at > datetime.utcnow(),
            )
            .options(selectinload(TeamInvitation.team))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def accept_invitation(
        self,
        token: str,
        user_id: uuid.UUID,
    ) -> Optional[TeamMember]:
        """招待を承諾"""
        invitation = await self.get_invitation_by_token(token)
        if not invitation:
            return None

        # メンバーとして追加
        member = await self.add_member(
            team_id=invitation.team_id,
            user_id=user_id,
            role=invitation.role,
        )

        # 招待を完了としてマーク
        invitation.accepted_at = datetime.utcnow()
        await self.db.commit()

        return member

    async def list_pending_invitations(self, team_id: uuid.UUID) -> list[TeamInvitation]:
        """保留中の招待一覧を取得"""
        query = select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.accepted_at.is_(None),
            TeamInvitation.expires_at > datetime.utcnow(),
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cancel_invitation(self, invitation_id: uuid.UUID) -> bool:
        """招待をキャンセル"""
        query = select(TeamInvitation).where(TeamInvitation.id == invitation_id)
        result = await self.db.execute(query)
        invitation = result.scalar_one_or_none()

        if not invitation:
            return False

        await self.db.delete(invitation)
        await self.db.commit()
        return True


class SharingService:
    """共有管理サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def share_with_team(
        self,
        transcription_id: uuid.UUID,
        team_id: uuid.UUID,
        permission: SharePermission,
        shared_by: uuid.UUID,
    ) -> TranscriptionShare:
        """チームに共有"""
        share = TranscriptionShare(
            transcription_id=transcription_id,
            team_id=team_id,
            permission=permission,
            shared_by=shared_by,
        )
        self.db.add(share)
        await self.db.commit()
        return share

    async def share_with_user(
        self,
        transcription_id: uuid.UUID,
        user_id: uuid.UUID,
        permission: SharePermission,
        shared_by: uuid.UUID,
    ) -> TranscriptionShare:
        """ユーザーに共有"""
        share = TranscriptionShare(
            transcription_id=transcription_id,
            user_id=user_id,
            permission=permission,
            shared_by=shared_by,
        )
        self.db.add(share)
        await self.db.commit()
        return share

    async def get_share_permission(
        self,
        transcription_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[SharePermission]:
        """ユーザーの共有権限を取得"""
        # 直接共有されている場合
        direct_query = select(TranscriptionShare).where(
            TranscriptionShare.transcription_id == transcription_id,
            TranscriptionShare.user_id == user_id,
        )
        result = await self.db.execute(direct_query)
        direct_share = result.scalar_one_or_none()
        if direct_share:
            return direct_share.permission

        # チーム経由で共有されている場合
        team_query = (
            select(TranscriptionShare)
            .join(Team)
            .join(TeamMember)
            .where(
                TranscriptionShare.transcription_id == transcription_id,
                TeamMember.user_id == user_id,
            )
        )
        result = await self.db.execute(team_query)
        team_share = result.scalar_one_or_none()
        if team_share:
            return team_share.permission

        return None

    async def list_transcription_shares(
        self,
        transcription_id: uuid.UUID,
    ) -> list[TranscriptionShare]:
        """文字起こしの共有一覧を取得"""
        query = (
            select(TranscriptionShare)
            .where(TranscriptionShare.transcription_id == transcription_id)
            .options(
                selectinload(TranscriptionShare.team),
                selectinload(TranscriptionShare.shared_with_user),
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_shared_with_me(
        self,
        user_id: uuid.UUID,
    ) -> list[TranscriptionShare]:
        """自分に共有された文字起こし一覧を取得"""
        # 直接共有とチーム経由の共有を取得
        query = (
            select(TranscriptionShare)
            .outerjoin(Team)
            .outerjoin(TeamMember, Team.id == TeamMember.team_id)
            .where(
                or_(
                    TranscriptionShare.user_id == user_id,
                    TeamMember.user_id == user_id,
                )
            )
            .options(selectinload(TranscriptionShare.transcription))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_share_permission(
        self,
        share_id: uuid.UUID,
        permission: SharePermission,
    ) -> Optional[TranscriptionShare]:
        """共有権限を更新"""
        query = select(TranscriptionShare).where(TranscriptionShare.id == share_id)
        result = await self.db.execute(query)
        share = result.scalar_one_or_none()

        if not share:
            return None

        share.permission = permission
        await self.db.commit()
        return share

    async def remove_share(self, share_id: uuid.UUID) -> bool:
        """共有を解除"""
        query = select(TranscriptionShare).where(TranscriptionShare.id == share_id)
        result = await self.db.execute(query)
        share = result.scalar_one_or_none()

        if not share:
            return False

        await self.db.delete(share)
        await self.db.commit()
        return True


class CommentService:
    """コメント管理サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_comment(
        self,
        transcription_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        segment_id: Optional[uuid.UUID] = None,
        timestamp_ms: Optional[str] = None,
        parent_id: Optional[uuid.UUID] = None,
    ) -> TranscriptionComment:
        """コメントを追加"""
        comment = TranscriptionComment(
            transcription_id=transcription_id,
            user_id=user_id,
            content=content,
            segment_id=segment_id,
            timestamp_ms=timestamp_ms,
            parent_id=parent_id,
        )
        self.db.add(comment)
        await self.db.commit()
        return comment

    async def get_comment(self, comment_id: uuid.UUID) -> Optional[TranscriptionComment]:
        """コメントを取得"""
        query = (
            select(TranscriptionComment)
            .where(TranscriptionComment.id == comment_id)
            .options(selectinload(TranscriptionComment.user))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_comments(
        self,
        transcription_id: uuid.UUID,
        segment_id: Optional[uuid.UUID] = None,
    ) -> list[TranscriptionComment]:
        """コメント一覧を取得"""
        query = (
            select(TranscriptionComment)
            .where(TranscriptionComment.transcription_id == transcription_id)
            .options(selectinload(TranscriptionComment.user))
            .order_by(TranscriptionComment.created_at)
        )

        if segment_id:
            query = query.where(TranscriptionComment.segment_id == segment_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_comment(
        self,
        comment_id: uuid.UUID,
        content: str,
    ) -> Optional[TranscriptionComment]:
        """コメントを更新"""
        comment = await self.get_comment(comment_id)
        if not comment:
            return None

        comment.content = content
        await self.db.commit()
        return comment

    async def delete_comment(self, comment_id: uuid.UUID) -> bool:
        """コメントを削除"""
        comment = await self.get_comment(comment_id)
        if not comment:
            return False

        await self.db.delete(comment)
        await self.db.commit()
        return True

    async def resolve_comment(
        self,
        comment_id: uuid.UUID,
        resolved: bool = True,
    ) -> Optional[TranscriptionComment]:
        """コメントを解決済みにする"""
        comment = await self.get_comment(comment_id)
        if not comment:
            return None

        comment.is_resolved = resolved
        await self.db.commit()
        return comment
