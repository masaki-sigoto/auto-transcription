"""コラボレーションAPIエンドポイント"""

import uuid
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.collaboration_service import (
    CollaborationService,
    CollaboratorRole,
    Operation,
    OperationType,
    CursorPosition,
)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_user_name() -> str:
    return "テストユーザー"


class JoinRoomRequest(BaseModel):
    role: str = "editor"


class CommentRequest(BaseModel):
    content: str
    segment_id: Optional[str] = None
    mentions: Optional[List[str]] = None
    parent_comment_id: Optional[str] = None


class CommentResponse(BaseModel):
    id: str
    transcription_id: str
    segment_id: Optional[str]
    user_id: str
    user_name: str
    content: str
    mentions: List[str]
    resolved: bool
    created_at: str
    replies: List[dict] = []


class OperationRequest(BaseModel):
    type: str
    segment_id: Optional[str] = None
    position: Optional[int] = None
    content: Optional[str] = None
    old_content: Optional[str] = None


class CursorRequest(BaseModel):
    segment_id: Optional[str] = None
    position: int


class SaveVersionRequest(BaseModel):
    description: Optional[str] = None


class VersionResponse(BaseModel):
    version: int
    created_at: str
    created_by: str
    description: Optional[str]


# WebSocket接続管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, transcription_id: str):
        await websocket.accept()
        if transcription_id not in self.active_connections:
            self.active_connections[transcription_id] = []
        self.active_connections[transcription_id].append(websocket)

    def disconnect(self, websocket: WebSocket, transcription_id: str):
        if transcription_id in self.active_connections:
            self.active_connections[transcription_id].remove(websocket)

    async def broadcast(self, transcription_id: str, message: dict):
        if transcription_id in self.active_connections:
            for connection in self.active_connections[transcription_id]:
                await connection.send_json(message)


manager = ConnectionManager()


@router.websocket("/ws/{transcription_id}")
async def websocket_collaboration(
    websocket: WebSocket,
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
):
    """リアルタイムコラボレーションWebSocket"""
    await manager.connect(websocket, transcription_id)

    service = CollaborationService(db)
    room = await service.get_room(transcription_id)

    try:
        # 初期データを送信
        members = await room.get_members()
        cursors = await room.get_cursors()
        version = await room.get_version()

        await websocket.send_json({
            "type": "init",
            "data": {
                "members": members,
                "cursors": [c.model_dump() for c in cursors],
                "version": version,
            },
        })

        # メッセージループ
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "join":
                user_id = data.get("user_id", str(uuid.uuid4()))
                user_name = data.get("user_name", "ゲスト")
                role = CollaboratorRole(data.get("role", "editor"))

                member = await room.join(user_id, user_name, role)
                await manager.broadcast(transcription_id, {
                    "type": "user_joined",
                    "data": member,
                })

            elif message_type == "cursor":
                cursor = CursorPosition(
                    user_id=data.get("user_id"),
                    user_name=data.get("user_name"),
                    segment_id=data.get("segment_id"),
                    position=data.get("position", 0),
                    color=data.get("color", "#3B82F6"),
                )
                await room.update_cursor(cursor)
                await manager.broadcast(transcription_id, {
                    "type": "cursor_moved",
                    "data": cursor.model_dump(),
                })

            elif message_type == "operation":
                from datetime import datetime

                operation = Operation(
                    id=str(uuid.uuid4()),
                    type=OperationType(data.get("operation_type")),
                    user_id=data.get("user_id"),
                    user_name=data.get("user_name"),
                    segment_id=data.get("segment_id"),
                    position=data.get("position"),
                    content=data.get("content"),
                    old_content=data.get("old_content"),
                    timestamp=datetime.utcnow().isoformat(),
                    version=0,
                )

                new_version = await room.apply_operation(operation)
                await manager.broadcast(transcription_id, {
                    "type": "operation",
                    "data": {
                        **data,
                        "version": new_version,
                    },
                })

            elif message_type == "leave":
                user_id = data.get("user_id")
                await room.leave(user_id)
                await manager.broadcast(transcription_id, {
                    "type": "user_left",
                    "data": {"user_id": user_id},
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, transcription_id)


@router.post("/{transcription_id}/join")
async def join_room(
    transcription_id: str,
    request: JoinRoomRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    user_name: str = Depends(get_current_user_name),
):
    """ルームに参加"""
    service = CollaborationService(db)
    room = await service.get_room(transcription_id)

    try:
        role = CollaboratorRole(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")

    member = await room.join(str(user_id), user_name, role)

    return {
        "status": "joined",
        "member": member,
        "transcription_id": transcription_id,
    }


@router.post("/{transcription_id}/leave")
async def leave_room(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ルームから退出"""
    service = CollaborationService(db)
    room = await service.get_room(transcription_id)

    await room.leave(str(user_id))

    return {"status": "left", "transcription_id": transcription_id}


@router.get("/{transcription_id}/members")
async def get_members(
    transcription_id: str,
    db: AsyncSession = Depends(get_db),
):
    """参加メンバーを取得"""
    service = CollaborationService(db)
    room = await service.get_room(transcription_id)

    members = await room.get_members()

    return {"members": members}


# コメント

@router.post("/{transcription_id}/comments", response_model=CommentResponse)
async def add_comment(
    transcription_id: str,
    request: CommentRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    user_name: str = Depends(get_current_user_name),
):
    """コメントを追加"""
    service = CollaborationService(db)

    segment_uuid = None
    if request.segment_id:
        try:
            segment_uuid = uuid.UUID(request.segment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid segment_id format")

    comment = await service.add_comment(
        transcription_id=uuid.UUID(transcription_id),
        user_id=user_id,
        user_name=user_name,
        content=request.content,
        segment_id=segment_uuid,
        parent_comment_id=request.parent_comment_id,
        mentions=request.mentions,
    )

    return CommentResponse(
        id=comment.id,
        transcription_id=comment.transcription_id,
        segment_id=comment.segment_id,
        user_id=comment.user_id,
        user_name=comment.user_name,
        content=comment.content,
        mentions=comment.mentions,
        resolved=comment.resolved,
        created_at=comment.created_at,
    )


@router.get("/{transcription_id}/comments", response_model=List[CommentResponse])
async def get_comments(
    transcription_id: str,
    segment_id: Optional[str] = None,
    include_resolved: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """コメントを取得"""
    service = CollaborationService(db)

    segment_uuid = None
    if segment_id:
        try:
            segment_uuid = uuid.UUID(segment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid segment_id format")

    comments = await service.get_comments(
        transcription_id=uuid.UUID(transcription_id),
        segment_id=segment_uuid,
        include_resolved=include_resolved,
    )

    return [
        CommentResponse(
            id=c.id,
            transcription_id=c.transcription_id,
            segment_id=c.segment_id,
            user_id=c.user_id,
            user_name=c.user_name,
            content=c.content,
            mentions=c.mentions,
            resolved=c.resolved,
            created_at=c.created_at,
            replies=[
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "content": r.content,
                    "created_at": r.created_at,
                }
                for r in c.replies
            ],
        )
        for c in comments
    ]


@router.post("/{transcription_id}/comments/{comment_id}/resolve")
async def resolve_comment(
    transcription_id: str,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """コメントを解決済みにする"""
    service = CollaborationService(db)

    success = await service.resolve_comment(
        comment_id=comment_id,
        user_id=user_id,
        transcription_id=uuid.UUID(transcription_id),
    )

    if not success:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {"status": "resolved", "comment_id": comment_id}


# バージョン管理

@router.post("/{transcription_id}/versions", response_model=VersionResponse)
async def save_version(
    transcription_id: str,
    request: SaveVersionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """現在の状態をバージョンとして保存"""
    service = CollaborationService(db)

    version = await service.save_version(
        transcription_id=uuid.UUID(transcription_id),
        user_id=user_id,
        description=request.description,
    )

    return VersionResponse(
        version=version.version,
        created_at=version.created_at,
        created_by=version.created_by,
        description=version.description,
    )


@router.get("/{transcription_id}/versions", response_model=List[VersionResponse])
async def get_version_history(
    transcription_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """バージョン履歴を取得"""
    service = CollaborationService(db)

    versions = await service.get_version_history(
        transcription_id=uuid.UUID(transcription_id),
        limit=limit,
    )

    return [
        VersionResponse(
            version=v.version,
            created_at=v.created_at,
            created_by=v.created_by,
            description=v.description,
        )
        for v in versions
    ]


@router.post("/{transcription_id}/versions/{version}/restore")
async def restore_version(
    transcription_id: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """指定バージョンに復元"""
    service = CollaborationService(db)

    success = await service.restore_version(
        transcription_id=uuid.UUID(transcription_id),
        version=version,
        user_id=user_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Version not found")

    return {"status": "restored", "version": version}
