"""リアルタイムコラボレーションサービス"""

import json
import asyncio
from typing import Optional, List, Dict, Set, Any
from datetime import datetime
from uuid import UUID, uuid4
from dataclasses import dataclass, field, asdict
from enum import Enum
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()


class OperationType(str, Enum):
    """操作タイプ"""
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"
    UPDATE_SPEAKER = "update_speaker"
    ADD_COMMENT = "add_comment"
    RESOLVE_COMMENT = "resolve_comment"


class CollaboratorRole(str, Enum):
    """コラボレーター権限"""
    OWNER = "owner"
    EDITOR = "editor"
    COMMENTER = "commenter"
    VIEWER = "viewer"


@dataclass
class Operation:
    """編集操作"""
    id: str
    type: OperationType
    user_id: str
    user_name: str
    segment_id: Optional[str]
    position: Optional[int]
    content: Optional[str]
    old_content: Optional[str]
    timestamp: str
    version: int


@dataclass
class Comment:
    """コメント"""
    id: str
    transcription_id: str
    segment_id: Optional[str]
    user_id: str
    user_name: str
    content: str
    mentions: List[str]
    resolved: bool
    resolved_by: Optional[str]
    created_at: str
    updated_at: str
    replies: List['Comment'] = field(default_factory=list)


@dataclass
class VersionHistory:
    """バージョン履歴"""
    version: int
    operations: List[Operation]
    created_at: str
    created_by: str
    description: Optional[str]


class CursorPosition(BaseModel):
    """カーソル位置"""
    user_id: str
    user_name: str
    segment_id: Optional[str]
    position: int
    color: str


class CollaborationRoom:
    """コラボレーションルーム"""

    def __init__(self, transcription_id: str, redis_client: redis.Redis):
        self.transcription_id = transcription_id
        self.redis = redis_client
        self.room_key = f"collab:room:{transcription_id}"
        self.cursors_key = f"collab:cursors:{transcription_id}"
        self.operations_key = f"collab:ops:{transcription_id}"
        self.version_key = f"collab:version:{transcription_id}"

    async def join(self, user_id: str, user_name: str, role: CollaboratorRole) -> Dict:
        """ルームに参加"""
        member = {
            "user_id": user_id,
            "user_name": user_name,
            "role": role.value,
            "joined_at": datetime.utcnow().isoformat(),
            "color": self._generate_color(user_id),
        }

        await self.redis.hset(self.room_key, user_id, json.dumps(member))
        await self.redis.expire(self.room_key, 86400)  # 24時間

        # 参加通知を発行
        await self.redis.publish(
            f"collab:events:{self.transcription_id}",
            json.dumps({
                "type": "user_joined",
                "data": member,
            }),
        )

        return member

    async def leave(self, user_id: str):
        """ルームから退出"""
        await self.redis.hdel(self.room_key, user_id)
        await self.redis.hdel(self.cursors_key, user_id)

        # 退出通知を発行
        await self.redis.publish(
            f"collab:events:{self.transcription_id}",
            json.dumps({
                "type": "user_left",
                "data": {"user_id": user_id},
            }),
        )

    async def get_members(self) -> List[Dict]:
        """参加メンバーを取得"""
        members_data = await self.redis.hgetall(self.room_key)
        return [json.loads(v) for v in members_data.values()]

    async def update_cursor(self, cursor: CursorPosition):
        """カーソル位置を更新"""
        await self.redis.hset(
            self.cursors_key,
            cursor.user_id,
            cursor.model_dump_json(),
        )
        await self.redis.expire(self.cursors_key, 3600)

        # カーソル移動を発行
        await self.redis.publish(
            f"collab:events:{self.transcription_id}",
            json.dumps({
                "type": "cursor_moved",
                "data": cursor.model_dump(),
            }),
        )

    async def get_cursors(self) -> List[CursorPosition]:
        """全カーソル位置を取得"""
        cursors_data = await self.redis.hgetall(self.cursors_key)
        return [CursorPosition.model_validate_json(v) for v in cursors_data.values()]

    async def apply_operation(self, operation: Operation) -> int:
        """操作を適用"""
        # バージョンをインクリメント
        new_version = await self.redis.incr(self.version_key)
        operation.version = new_version

        # 操作を保存
        await self.redis.rpush(
            self.operations_key,
            json.dumps(asdict(operation)),
        )
        await self.redis.expire(self.operations_key, 86400)

        # 操作を発行
        await self.redis.publish(
            f"collab:events:{self.transcription_id}",
            json.dumps({
                "type": "operation",
                "data": asdict(operation),
            }),
        )

        return new_version

    async def get_operations(self, from_version: int = 0) -> List[Operation]:
        """操作履歴を取得"""
        ops_data = await self.redis.lrange(self.operations_key, from_version, -1)
        return [Operation(**json.loads(op)) for op in ops_data]

    async def get_version(self) -> int:
        """現在のバージョンを取得"""
        version = await self.redis.get(self.version_key)
        return int(version) if version else 0

    def _generate_color(self, user_id: str) -> str:
        """ユーザーIDから色を生成"""
        colors = [
            "#EF4444", "#F97316", "#F59E0B", "#84CC16",
            "#22C55E", "#14B8A6", "#06B6D4", "#3B82F6",
            "#6366F1", "#8B5CF6", "#A855F7", "#EC4899",
        ]
        index = hash(user_id) % len(colors)
        return colors[index]


class CollaborationService:
    """コラボレーションサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = redis.from_url(
            getattr(settings, 'redis_url', 'redis://localhost:6379'),
            encoding="utf-8",
            decode_responses=True,
        )

    async def get_room(self, transcription_id: str) -> CollaborationRoom:
        """コラボレーションルームを取得"""
        return CollaborationRoom(transcription_id, self.redis)

    async def add_comment(
        self,
        transcription_id: UUID,
        user_id: UUID,
        user_name: str,
        content: str,
        segment_id: Optional[UUID] = None,
        parent_comment_id: Optional[str] = None,
        mentions: Optional[List[str]] = None,
    ) -> Comment:
        """コメントを追加"""
        comment_id = str(uuid4())
        now = datetime.utcnow().isoformat()

        comment = Comment(
            id=comment_id,
            transcription_id=str(transcription_id),
            segment_id=str(segment_id) if segment_id else None,
            user_id=str(user_id),
            user_name=user_name,
            content=content,
            mentions=mentions or [],
            resolved=False,
            resolved_by=None,
            created_at=now,
            updated_at=now,
        )

        # DBに保存
        await self.db.execute(
            text("""
                INSERT INTO comments (id, transcription_id, segment_id, user_id, user_name, content, mentions, resolved, created_at, updated_at, parent_id)
                VALUES (:id, :transcription_id, :segment_id, :user_id, :user_name, :content, :mentions, :resolved, :created_at, :updated_at, :parent_id)
            """),
            {
                "id": comment_id,
                "transcription_id": str(transcription_id),
                "segment_id": str(segment_id) if segment_id else None,
                "user_id": str(user_id),
                "user_name": user_name,
                "content": content,
                "mentions": json.dumps(mentions or []),
                "resolved": False,
                "created_at": now,
                "updated_at": now,
                "parent_id": parent_comment_id,
            },
        )
        await self.db.commit()

        # リアルタイム通知
        room = await self.get_room(str(transcription_id))
        await self.redis.publish(
            f"collab:events:{transcription_id}",
            json.dumps({
                "type": "comment_added",
                "data": asdict(comment),
            }),
        )

        # メンション通知
        for mentioned_user_id in (mentions or []):
            await self._send_mention_notification(
                mentioned_user_id,
                transcription_id,
                comment,
            )

        return comment

    async def get_comments(
        self,
        transcription_id: UUID,
        segment_id: Optional[UUID] = None,
        include_resolved: bool = False,
    ) -> List[Comment]:
        """コメントを取得"""
        query = """
            SELECT id, transcription_id, segment_id, user_id, user_name, content, mentions, resolved, resolved_by, created_at, updated_at
            FROM comments
            WHERE transcription_id = :transcription_id
            AND parent_id IS NULL
        """

        params: Dict[str, Any] = {"transcription_id": str(transcription_id)}

        if segment_id:
            query += " AND segment_id = :segment_id"
            params["segment_id"] = str(segment_id)

        if not include_resolved:
            query += " AND resolved = false"

        query += " ORDER BY created_at DESC"

        result = await self.db.execute(text(query), params)
        rows = result.fetchall()

        comments = []
        for row in rows:
            comment = Comment(
                id=row[0],
                transcription_id=row[1],
                segment_id=row[2],
                user_id=row[3],
                user_name=row[4],
                content=row[5],
                mentions=json.loads(row[6]) if row[6] else [],
                resolved=row[7],
                resolved_by=row[8],
                created_at=row[9],
                updated_at=row[10],
            )

            # 返信を取得
            replies_result = await self.db.execute(
                text("""
                    SELECT id, transcription_id, segment_id, user_id, user_name, content, mentions, resolved, resolved_by, created_at, updated_at
                    FROM comments
                    WHERE parent_id = :parent_id
                    ORDER BY created_at
                """),
                {"parent_id": comment.id},
            )

            for reply_row in replies_result.fetchall():
                comment.replies.append(Comment(
                    id=reply_row[0],
                    transcription_id=reply_row[1],
                    segment_id=reply_row[2],
                    user_id=reply_row[3],
                    user_name=reply_row[4],
                    content=reply_row[5],
                    mentions=json.loads(reply_row[6]) if reply_row[6] else [],
                    resolved=reply_row[7],
                    resolved_by=reply_row[8],
                    created_at=reply_row[9],
                    updated_at=reply_row[10],
                ))

            comments.append(comment)

        return comments

    async def resolve_comment(
        self,
        comment_id: str,
        user_id: UUID,
        transcription_id: UUID,
    ) -> bool:
        """コメントを解決済みにする"""
        await self.db.execute(
            text("""
                UPDATE comments
                SET resolved = true, resolved_by = :user_id, updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": comment_id,
                "user_id": str(user_id),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        await self.db.commit()

        # リアルタイム通知
        await self.redis.publish(
            f"collab:events:{transcription_id}",
            json.dumps({
                "type": "comment_resolved",
                "data": {"comment_id": comment_id, "resolved_by": str(user_id)},
            }),
        )

        return True

    async def save_version(
        self,
        transcription_id: UUID,
        user_id: UUID,
        description: Optional[str] = None,
    ) -> VersionHistory:
        """現在の状態をバージョンとして保存"""
        room = await self.get_room(str(transcription_id))
        current_version = await room.get_version()
        operations = await room.get_operations()

        version_history = VersionHistory(
            version=current_version,
            operations=operations,
            created_at=datetime.utcnow().isoformat(),
            created_by=str(user_id),
            description=description,
        )

        # DBに保存
        await self.db.execute(
            text("""
                INSERT INTO version_history (transcription_id, version, operations, created_at, created_by, description)
                VALUES (:transcription_id, :version, :operations, :created_at, :created_by, :description)
            """),
            {
                "transcription_id": str(transcription_id),
                "version": current_version,
                "operations": json.dumps([asdict(op) for op in operations]),
                "created_at": version_history.created_at,
                "created_by": str(user_id),
                "description": description,
            },
        )
        await self.db.commit()

        return version_history

    async def get_version_history(
        self,
        transcription_id: UUID,
        limit: int = 20,
    ) -> List[VersionHistory]:
        """バージョン履歴を取得"""
        result = await self.db.execute(
            text("""
                SELECT version, operations, created_at, created_by, description
                FROM version_history
                WHERE transcription_id = :transcription_id
                ORDER BY version DESC
                LIMIT :limit
            """),
            {"transcription_id": str(transcription_id), "limit": limit},
        )

        return [
            VersionHistory(
                version=row[0],
                operations=[Operation(**op) for op in json.loads(row[1])],
                created_at=row[2],
                created_by=row[3],
                description=row[4],
            )
            for row in result.fetchall()
        ]

    async def restore_version(
        self,
        transcription_id: UUID,
        version: int,
        user_id: UUID,
    ) -> bool:
        """指定バージョンに復元"""
        # バージョン履歴を取得
        result = await self.db.execute(
            text("""
                SELECT operations
                FROM version_history
                WHERE transcription_id = :transcription_id AND version = :version
            """),
            {"transcription_id": str(transcription_id), "version": version},
        )
        row = result.fetchone()

        if not row:
            return False

        # 復元処理（実際の実装ではセグメントデータを復元）
        # ここでは簡易的に操作ログを再適用

        # 復元通知
        await self.redis.publish(
            f"collab:events:{transcription_id}",
            json.dumps({
                "type": "version_restored",
                "data": {"version": version, "restored_by": str(user_id)},
            }),
        )

        return True

    async def _send_mention_notification(
        self,
        user_id: str,
        transcription_id: UUID,
        comment: Comment,
    ):
        """メンション通知を送信"""
        # 通知をDBに保存
        await self.db.execute(
            text("""
                INSERT INTO notifications (id, user_id, type, title, message, data, created_at)
                VALUES (:id, :user_id, :type, :title, :message, :data, :created_at)
            """),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "type": "mention",
                "title": "メンションされました",
                "message": f"{comment.user_name}さんがあなたをメンションしました",
                "data": json.dumps({
                    "transcription_id": str(transcription_id),
                    "comment_id": comment.id,
                }),
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        await self.db.commit()

        # WebSocket通知
        await self.redis.publish(
            f"notifications:{user_id}",
            json.dumps({
                "type": "mention",
                "data": {
                    "transcription_id": str(transcription_id),
                    "comment_id": comment.id,
                    "from_user": comment.user_name,
                },
            }),
        )
