import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import uuid

from app.models.audit import AuditLog, SecurityPolicy
from app.services.audit_service import AuditService, SecurityPolicyService


class TestAuditLogAPI:
    """監査ログAPIのテスト"""

    @pytest.mark.asyncio
    async def test_list_audit_logs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """監査ログ一覧を取得"""
        # 監査ログを作成
        logs = [
            AuditLog(
                user_id=test_user.id,
                action="login",
                resource_type="session",
                ip_address="127.0.0.1",
            ),
            AuditLog(
                user_id=test_user.id,
                action="create",
                resource_type="transcription",
                resource_id=str(uuid.uuid4()),
                ip_address="127.0.0.1",
            ),
        ]
        db_session.add_all(logs)
        await db_session.commit()

        response = await client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 2

    @pytest.mark.asyncio
    async def test_filter_audit_logs_by_action(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """アクションでフィルター"""
        logs = [
            AuditLog(
                user_id=test_user.id,
                action="login",
                resource_type="session",
            ),
            AuditLog(
                user_id=test_user.id,
                action="create",
                resource_type="transcription",
            ),
            AuditLog(
                user_id=test_user.id,
                action="delete",
                resource_type="transcription",
            ),
        ]
        db_session.add_all(logs)
        await db_session.commit()

        response = await client.get(
            "/api/v1/admin/audit-logs",
            params={"action": "login"},
        )
        assert response.status_code == 200

        data = response.json()
        assert all(log["action"] == "login" for log in data)

    @pytest.mark.asyncio
    async def test_filter_audit_logs_by_date(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """日付でフィルター"""
        response = await client.get(
            "/api/v1/admin/audit-logs",
            params={
                "start_date": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "end_date": datetime.utcnow().isoformat(),
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_audit_logs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """監査ログをエクスポート"""
        log = AuditLog(
            user_id=test_user.id,
            action="test",
            resource_type="test",
        )
        db_session.add(log)
        await db_session.commit()

        response = await client.get(
            "/api/v1/admin/audit-logs/export",
            params={"format": "csv"},
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]


class TestSecurityPolicyAPI:
    """セキュリティポリシーAPIのテスト"""

    @pytest.mark.asyncio
    async def test_get_security_policy(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """セキュリティポリシーを取得"""
        policy = SecurityPolicy(
            user_id=test_user.id,
            password_min_length=8,
            require_mfa=False,
            session_timeout_minutes=60,
            max_login_attempts=5,
        )
        db_session.add(policy)
        await db_session.commit()

        response = await client.get("/api/v1/admin/security-policy")
        assert response.status_code == 200

        data = response.json()
        assert data["password_min_length"] == 8
        assert data["session_timeout_minutes"] == 60

    @pytest.mark.asyncio
    async def test_update_security_policy(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """セキュリティポリシーを更新"""
        policy = SecurityPolicy(
            user_id=test_user.id,
            password_min_length=8,
            require_mfa=False,
        )
        db_session.add(policy)
        await db_session.commit()

        response = await client.patch(
            "/api/v1/admin/security-policy",
            json={
                "password_min_length": 12,
                "require_mfa": True,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["password_min_length"] == 12
        assert data["require_mfa"] is True


class TestUserManagementAPI:
    """ユーザー管理APIのテスト"""

    @pytest.mark.asyncio
    async def test_list_users(self, client: AsyncClient, test_user):
        """ユーザー一覧を取得"""
        response = await client.get("/api/v1/admin/users")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_user_details(self, client: AsyncClient, test_user):
        """ユーザー詳細を取得"""
        response = await client.get(f"/api/v1/admin/users/{test_user.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_suspend_user(self, client: AsyncClient, test_user):
        """ユーザーを停止"""
        response = await client.post(
            f"/api/v1/admin/users/{test_user.id}/suspend",
            json={"reason": "テスト停止"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["is_suspended"] is True

    @pytest.mark.asyncio
    async def test_unsuspend_user(self, client: AsyncClient, test_user):
        """ユーザーの停止を解除"""
        # 先に停止
        await client.post(
            f"/api/v1/admin/users/{test_user.id}/suspend",
            json={"reason": "テスト停止"},
        )

        # 停止解除
        response = await client.post(f"/api/v1/admin/users/{test_user.id}/unsuspend")
        assert response.status_code == 200

        data = response.json()
        assert data["is_suspended"] is False


class TestAuditService:
    """AuditServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_log_action(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """アクションをログに記録"""
        service = AuditService(db_session)

        log = await service.log_action(
            user_id=test_user.id,
            action="create",
            resource_type="transcription",
            resource_id=str(uuid.uuid4()),
            details={"title": "テスト文字起こし"},
            ip_address="192.168.1.1",
        )

        assert log.action == "create"
        assert log.resource_type == "transcription"
        assert log.details["title"] == "テスト文字起こし"

    @pytest.mark.asyncio
    async def test_get_user_activity(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """ユーザーのアクティビティを取得"""
        service = AuditService(db_session)

        # いくつかのアクションをログ
        for i in range(5):
            await service.log_action(
                user_id=test_user.id,
                action=f"action_{i}",
                resource_type="test",
            )

        activities = await service.get_user_activity(
            user_id=test_user.id,
            limit=10,
        )

        assert len(activities) == 5


class TestSecurityPolicyService:
    """SecurityPolicyServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_validate_password(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """パスワードを検証"""
        policy = SecurityPolicy(
            user_id=test_user.id,
            password_min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_numbers=True,
            require_special_chars=True,
        )
        db_session.add(policy)
        await db_session.commit()

        service = SecurityPolicyService(db_session)

        # 有効なパスワード
        is_valid, errors = await service.validate_password(
            user_id=test_user.id,
            password="Password123!",
        )
        assert is_valid is True
        assert len(errors) == 0

        # 無効なパスワード（短すぎる）
        is_valid, errors = await service.validate_password(
            user_id=test_user.id,
            password="Pass1!",
        )
        assert is_valid is False
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_check_login_attempts(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """ログイン試行をチェック"""
        policy = SecurityPolicy(
            user_id=test_user.id,
            max_login_attempts=3,
            lockout_duration_minutes=30,
        )
        db_session.add(policy)
        await db_session.commit()

        service = SecurityPolicyService(db_session)

        # ログイン試行を記録
        for _ in range(3):
            await service.record_login_attempt(
                user_id=test_user.id,
                success=False,
            )

        # アカウントがロックされているか確認
        is_locked = await service.is_account_locked(user_id=test_user.id)
        assert is_locked is True
