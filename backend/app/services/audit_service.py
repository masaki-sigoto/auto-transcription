import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import Request

from app.models.audit import AuditLog, AuditAction, APIKey, SecurityPolicy


class AuditService:
    """監査ログサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        user_id: Optional[uuid.UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[uuid.UUID] = None,
        details: Optional[dict] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        request: Optional[Request] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """監査ログを記録"""
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            old_value=old_value,
            new_value=new_value,
            status=status,
            error_message=error_message,
        )

        # リクエスト情報を追加
        if request:
            log_entry.ip_address = self._get_client_ip(request)
            log_entry.user_agent = request.headers.get("user-agent", "")[:500]
            log_entry.request_method = request.method
            log_entry.request_path = str(request.url.path)[:500]

        self.db.add(log_entry)
        await self.db.commit()
        return log_entry

    def _get_client_ip(self, request: Request) -> str:
        """クライアントIPを取得"""
        # プロキシ経由の場合
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # 直接接続の場合
        if request.client:
            return request.client.host

        return "unknown"

    async def list_logs(
        self,
        user_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """監査ログを検索"""
        query = select(AuditLog).options(selectinload(AuditLog.user))
        count_query = select(AuditLog)

        # フィルタ条件を追加
        conditions = []
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditLog.resource_id == resource_id)
        if start_date:
            conditions.append(AuditLog.created_at >= start_date)
        if end_date:
            conditions.append(AuditLog.created_at <= end_date)
        if status:
            conditions.append(AuditLog.status == status)

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # 件数を取得
        from sqlalchemy import func
        count_result = await self.db.execute(select(func.count()).select_from(count_query.subquery()))
        total = count_result.scalar() or 0

        # 結果を取得
        query = query.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def get_user_activity(
        self,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> list[AuditLog]:
        """ユーザーのアクティビティを取得"""
        start_date = datetime.utcnow() - timedelta(days=days)

        query = (
            select(AuditLog)
            .where(
                AuditLog.user_id == user_id,
                AuditLog.created_at >= start_date,
            )
            .order_by(desc(AuditLog.created_at))
            .limit(100)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_security_events(
        self,
        days: int = 7,
    ) -> list[AuditLog]:
        """セキュリティ関連イベントを取得"""
        start_date = datetime.utcnow() - timedelta(days=days)
        security_actions = [
            AuditAction.LOGIN_FAILED.value,
            AuditAction.PASSWORD_CHANGED.value,
            AuditAction.MFA_ENABLED.value,
            AuditAction.MFA_DISABLED.value,
            AuditAction.API_KEY_CREATED.value,
            AuditAction.API_KEY_REVOKED.value,
        ]

        query = (
            select(AuditLog)
            .where(
                AuditLog.action.in_(security_actions),
                AuditLog.created_at >= start_date,
            )
            .options(selectinload(AuditLog.user))
            .order_by(desc(AuditLog.created_at))
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def export_logs(
        self,
        start_date: datetime,
        end_date: datetime,
        format: str = "json",
    ) -> str:
        """監査ログをエクスポート"""
        logs, _ = await self.list_logs(
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        if format == "json":
            import json
            return json.dumps([
                {
                    "id": str(log.id),
                    "user_id": str(log.user_id) if log.user_id else None,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": str(log.resource_id) if log.resource_id else None,
                    "ip_address": log.ip_address,
                    "status": log.status,
                    "details": log.details,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ], indent=2, ensure_ascii=False)

        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ID", "User ID", "Action", "Resource Type", "Resource ID",
                "IP Address", "Status", "Created At"
            ])

            for log in logs:
                writer.writerow([
                    str(log.id),
                    str(log.user_id) if log.user_id else "",
                    log.action,
                    log.resource_type or "",
                    str(log.resource_id) if log.resource_id else "",
                    log.ip_address or "",
                    log.status,
                    log.created_at.isoformat(),
                ])

            return output.getvalue()

        return ""


class APIKeyService:
    """APIキー管理サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_key(self, key: str) -> str:
        """キーをハッシュ化"""
        return hashlib.sha256(key.encode()).hexdigest()

    async def create_key(
        self,
        user_id: uuid.UUID,
        name: str,
        scopes: list[str] = None,
        expires_days: Optional[int] = None,
    ) -> tuple[APIKey, str]:
        """APIキーを作成（キーは一度だけ返す）"""
        # キーを生成
        raw_key = f"sk_{secrets.token_urlsafe(32)}"
        key_prefix = raw_key[:10]
        key_hash = self._hash_key(raw_key)

        # 有効期限
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)

        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or [],
            expires_at=expires_at,
        )

        self.db.add(api_key)
        await self.db.commit()

        return api_key, raw_key

    async def validate_key(self, raw_key: str) -> Optional[APIKey]:
        """APIキーを検証"""
        key_hash = self._hash_key(raw_key)

        query = select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.revoked_at.is_(None),
        )
        result = await self.db.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # 有効期限チェック
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        # 最終使用日時を更新
        api_key.last_used_at = datetime.utcnow()
        await self.db.commit()

        return api_key

    async def list_keys(self, user_id: uuid.UUID) -> list[APIKey]:
        """ユーザーのAPIキー一覧を取得"""
        query = (
            select(APIKey)
            .where(
                APIKey.user_id == user_id,
                APIKey.revoked_at.is_(None),
            )
            .order_by(desc(APIKey.created_at))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def revoke_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """APIキーを取り消し"""
        query = select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == user_id,
        )
        result = await self.db.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            return False

        api_key.revoked_at = datetime.utcnow()
        await self.db.commit()
        return True


class SecurityPolicyService:
    """セキュリティポリシー管理サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy(self, name: str = "default") -> Optional[SecurityPolicy]:
        """ポリシーを取得"""
        query = select(SecurityPolicy).where(SecurityPolicy.name == name)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_default(self) -> SecurityPolicy:
        """デフォルトポリシーを取得または作成"""
        policy = await self.get_policy("default")
        if not policy:
            policy = SecurityPolicy(name="default")
            self.db.add(policy)
            await self.db.commit()
        return policy

    async def update_policy(
        self,
        name: str = "default",
        **kwargs,
    ) -> Optional[SecurityPolicy]:
        """ポリシーを更新"""
        policy = await self.get_policy(name)
        if not policy:
            return None

        for key, value in kwargs.items():
            if hasattr(policy, key) and value is not None:
                setattr(policy, key, str(value) if not isinstance(value, (list, dict)) else value)

        await self.db.commit()
        return policy

    def validate_password(self, password: str, policy: SecurityPolicy) -> tuple[bool, list[str]]:
        """パスワードをポリシーに基づいて検証"""
        errors = []

        min_length = int(policy.password_min_length)
        if len(password) < min_length:
            errors.append(f"パスワードは{min_length}文字以上である必要があります")

        if policy.password_require_uppercase == "true" and not any(c.isupper() for c in password):
            errors.append("大文字を含める必要があります")

        if policy.password_require_lowercase == "true" and not any(c.islower() for c in password):
            errors.append("小文字を含める必要があります")

        if policy.password_require_numbers == "true" and not any(c.isdigit() for c in password):
            errors.append("数字を含める必要があります")

        if policy.password_require_special == "true":
            special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
            if not any(c in special_chars for c in password):
                errors.append("特殊文字を含める必要があります")

        return len(errors) == 0, errors

    def check_ip_whitelist(self, ip_address: str, policy: SecurityPolicy) -> bool:
        """IPホワイトリストをチェック"""
        if policy.ip_whitelist_enabled != "true":
            return True

        if not policy.ip_whitelist:
            return True

        return ip_address in policy.ip_whitelist
