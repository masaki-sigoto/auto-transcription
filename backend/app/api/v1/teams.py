import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.core.database import get_db
from app.models.team import TeamRole, SharePermission
from app.services.team_service import TeamService, SharingService, CommentService

router = APIRouter(prefix="/teams", tags=["teams"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================

class CreateTeamRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateTeamRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: Optional[str] = None
    name: Optional[str] = None
    role: TeamRole
    joined_at: str


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    members_count: int
    created_at: str


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: TeamRole = TeamRole.MEMBER


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: TeamRole
    expires_at: str
    invite_link: str


class UpdateMemberRoleRequest(BaseModel):
    role: TeamRole


class ShareRequest(BaseModel):
    transcription_id: uuid.UUID
    permission: SharePermission = SharePermission.VIEW


class ShareWithUserRequest(BaseModel):
    transcription_id: uuid.UUID
    user_email: EmailStr
    permission: SharePermission = SharePermission.VIEW


class ShareResponse(BaseModel):
    id: uuid.UUID
    transcription_id: uuid.UUID
    team_id: Optional[uuid.UUID]
    user_id: Optional[uuid.UUID]
    permission: SharePermission
    created_at: str


class CommentRequest(BaseModel):
    content: str
    segment_id: Optional[uuid.UUID] = None
    timestamp_ms: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class CommentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: Optional[str]
    content: str
    segment_id: Optional[uuid.UUID]
    timestamp_ms: Optional[str]
    parent_id: Optional[uuid.UUID]
    is_resolved: bool
    created_at: str


# =============================================================================
# チーム管理
# =============================================================================

@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    request: CreateTeamRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームを作成"""
    service = TeamService(db)
    team = await service.create_team(
        name=request.name,
        owner_id=user_id,
        description=request.description,
    )

    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        members_count=1,
        created_at=team.created_at.isoformat(),
    )


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ユーザーが所属するチーム一覧を取得"""
    service = TeamService(db)
    teams = await service.list_user_teams(user_id)

    return [
        TeamResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            members_count=len(t.members),
            created_at=t.created_at.isoformat(),
        )
        for t in teams
    ]


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームを取得"""
    service = TeamService(db)

    # 権限チェック
    role = await service.get_member_role(team_id, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    team = await service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        members_count=len(team.members),
        created_at=team.created_at.isoformat(),
    )


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    request: UpdateTeamRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームを更新"""
    service = TeamService(db)

    # 権限チェック（オーナーまたは管理者のみ）
    role = await service.get_member_role(team_id, user_id)
    if role not in [TeamRole.OWNER, TeamRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only owner or admin can update team")

    team = await service.update_team(
        team_id=team_id,
        name=request.name,
        description=request.description,
    )

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        members_count=len(team.members),
        created_at=team.created_at.isoformat(),
    )


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームを削除"""
    service = TeamService(db)

    # 権限チェック（オーナーのみ）
    role = await service.get_member_role(team_id, user_id)
    if role != TeamRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owner can delete team")

    if not await service.delete_team(team_id):
        raise HTTPException(status_code=404, detail="Team not found")


# =============================================================================
# メンバー管理
# =============================================================================

@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_members(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームメンバー一覧を取得"""
    service = TeamService(db)

    role = await service.get_member_role(team_id, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    members = await service.list_team_members(team_id)

    return [
        TeamMemberResponse(
            id=m.id,
            user_id=m.user_id,
            email=m.user.email if m.user else None,
            name=m.user.name if m.user else None,
            role=m.role,
            joined_at=m.joined_at.isoformat(),
        )
        for m in members
    ]


@router.post("/{team_id}/invite", response_model=InvitationResponse)
async def invite_member(
    team_id: uuid.UUID,
    request: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メンバーを招待"""
    service = TeamService(db)

    # 権限チェック（オーナー、管理者のみ）
    role = await service.get_member_role(team_id, user_id)
    if role not in [TeamRole.OWNER, TeamRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only owner or admin can invite members")

    invitation = await service.create_invitation(
        team_id=team_id,
        email=request.email,
        invited_by=user_id,
        role=request.role,
    )

    # 招待リンクを生成（フロントエンドのURLを使用）
    invite_link = f"/teams/join?token={invitation.token}"

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at.isoformat(),
        invite_link=invite_link,
    )


@router.post("/join")
async def join_team(
    token: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """招待を承諾してチームに参加"""
    service = TeamService(db)

    member = await service.accept_invitation(token, user_id)
    if not member:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    return {"message": "Successfully joined team"}


@router.patch("/{team_id}/members/{member_user_id}/role")
async def update_member_role(
    team_id: uuid.UUID,
    member_user_id: uuid.UUID,
    request: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メンバーのロールを更新"""
    service = TeamService(db)

    # 権限チェック（オーナーのみ）
    role = await service.get_member_role(team_id, user_id)
    if role != TeamRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owner can change roles")

    member = await service.update_member_role(team_id, member_user_id, request.role)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    return {"message": "Role updated successfully"}


@router.delete("/{team_id}/members/{member_user_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    member_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """メンバーを削除"""
    service = TeamService(db)

    # 権限チェック（オーナー、管理者のみ、または自分自身）
    role = await service.get_member_role(team_id, user_id)
    is_self = user_id == member_user_id

    if not is_self and role not in [TeamRole.OWNER, TeamRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    if not await service.remove_member(team_id, member_user_id):
        raise HTTPException(status_code=404, detail="Member not found")


# =============================================================================
# 共有管理
# =============================================================================

@router.post("/{team_id}/share", response_model=ShareResponse)
async def share_with_team(
    team_id: uuid.UUID,
    request: ShareRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """チームに文字起こしを共有"""
    team_service = TeamService(db)
    sharing_service = SharingService(db)

    # チームメンバーであることを確認
    role = await team_service.get_member_role(team_id, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    share = await sharing_service.share_with_team(
        transcription_id=request.transcription_id,
        team_id=team_id,
        permission=request.permission,
        shared_by=user_id,
    )

    return ShareResponse(
        id=share.id,
        transcription_id=share.transcription_id,
        team_id=share.team_id,
        user_id=share.user_id,
        permission=share.permission,
        created_at=share.created_at.isoformat(),
    )


# =============================================================================
# コメント管理
# =============================================================================

@router.post("/transcriptions/{transcription_id}/comments", response_model=CommentResponse)
async def add_comment(
    transcription_id: uuid.UUID,
    request: CommentRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コメントを追加"""
    comment_service = CommentService(db)

    comment = await comment_service.add_comment(
        transcription_id=transcription_id,
        user_id=user_id,
        content=request.content,
        segment_id=request.segment_id,
        timestamp_ms=request.timestamp_ms,
        parent_id=request.parent_id,
    )

    return CommentResponse(
        id=comment.id,
        user_id=comment.user_id,
        user_name=None,
        content=comment.content,
        segment_id=comment.segment_id,
        timestamp_ms=comment.timestamp_ms,
        parent_id=comment.parent_id,
        is_resolved=comment.is_resolved,
        created_at=comment.created_at.isoformat(),
    )


@router.get("/transcriptions/{transcription_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    transcription_id: uuid.UUID,
    segment_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コメント一覧を取得"""
    comment_service = CommentService(db)

    comments = await comment_service.list_comments(transcription_id, segment_id)

    return [
        CommentResponse(
            id=c.id,
            user_id=c.user_id,
            user_name=c.user.name if c.user else None,
            content=c.content,
            segment_id=c.segment_id,
            timestamp_ms=c.timestamp_ms,
            parent_id=c.parent_id,
            is_resolved=c.is_resolved,
            created_at=c.created_at.isoformat(),
        )
        for c in comments
    ]


@router.patch("/comments/{comment_id}/resolve")
async def resolve_comment(
    comment_id: uuid.UUID,
    resolved: bool = True,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コメントを解決済みにする"""
    comment_service = CommentService(db)

    comment = await comment_service.resolve_comment(comment_id, resolved)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {"message": "Comment resolved" if resolved else "Comment reopened"}


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コメントを削除"""
    comment_service = CommentService(db)

    comment = await comment_service.get_comment(comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # 自分のコメントのみ削除可能
    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only delete your own comments")

    await comment_service.delete_comment(comment_id)
