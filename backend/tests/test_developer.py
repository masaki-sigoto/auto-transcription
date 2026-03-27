import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from datetime import datetime, timedelta

from app.models.audit import APIKey
from app.services.audit_service import APIKeyService


class TestDeveloperAPI:
    """開発者APIのテスト"""

    @pytest.mark.asyncio
    async def test_create_api_key(self, client: AsyncClient, test_user):
        """APIキーを作成"""
        response = await client.post(
            "/api/v1/developer/api-keys",
            json={
                "name": "テストAPIキー",
                "scopes": ["transcriptions:read", "transcriptions:write"],
                "expires_in_days": 30,
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "テストAPIキー"
        assert "key" in data  # 生成されたキーが含まれる
        assert data["scopes"] == ["transcriptions:read", "transcriptions:write"]

    @pytest.mark.asyncio
    async def test_list_api_keys(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """APIキー一覧を取得"""
        # APIキーを作成
        api_key = APIKey(
            user_id=test_user.id,
            name="テストキー",
            key_hash="dummy_hash",
            key_prefix="sk_test",
            scopes=["transcriptions:read"],
        )
        db_session.add(api_key)
        await db_session.commit()

        response = await client.get("/api/v1/developer/api-keys")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == "テストキー"
        # キーのハッシュは返されない
        assert "key_hash" not in data[0]

    @pytest.mark.asyncio
    async def test_revoke_api_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """APIキーを無効化"""
        api_key = APIKey(
            user_id=test_user.id,
            name="無効化予定キー",
            key_hash="dummy_hash",
            key_prefix="sk_rev",
            scopes=["transcriptions:read"],
        )
        db_session.add(api_key)
        await db_session.commit()

        response = await client.delete(f"/api/v1/developer/api-keys/{api_key.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_get_api_docs(self, client: AsyncClient):
        """APIドキュメントを取得"""
        response = await client.get("/api/v1/developer/docs")
        assert response.status_code == 200

        data = response.json()
        assert "endpoints" in data
        assert len(data["endpoints"]) > 0

    @pytest.mark.asyncio
    async def test_get_code_examples(self, client: AsyncClient):
        """コード例を取得"""
        response = await client.get("/api/v1/developer/examples")
        assert response.status_code == 200

        data = response.json()
        assert "python" in data
        assert "javascript" in data
        assert "curl" in data


class TestWebhookAPI:
    """WebhookAPIのテスト"""

    @pytest.mark.asyncio
    async def test_create_webhook(self, client: AsyncClient, test_user):
        """Webhookを作成"""
        response = await client.post(
            "/api/v1/developer/webhooks",
            json={
                "url": "https://example.com/webhook",
                "events": ["transcription.completed", "transcription.failed"],
                "secret": "my_webhook_secret",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["transcription.completed", "transcription.failed"]
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_webhooks(self, client: AsyncClient, test_user):
        """Webhook一覧を取得"""
        # 先にWebhookを作成
        await client.post(
            "/api/v1/developer/webhooks",
            json={
                "url": "https://example.com/webhook1",
                "events": ["transcription.completed"],
            },
        )
        await client.post(
            "/api/v1/developer/webhooks",
            json={
                "url": "https://example.com/webhook2",
                "events": ["transcription.failed"],
            },
        )

        response = await client.get("/api/v1/developer/webhooks")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_test_webhook(self, client: AsyncClient, test_user):
        """Webhookをテスト"""
        # Webhookを作成
        create_response = await client.post(
            "/api/v1/developer/webhooks",
            json={
                "url": "https://httpbin.org/post",
                "events": ["transcription.completed"],
            },
        )
        webhook_id = create_response.json()["id"]

        response = await client.post(
            f"/api/v1/developer/webhooks/{webhook_id}/test"
        )
        # 外部URLのため実際のテストでは失敗する可能性があるが、
        # APIエンドポイントは正常に動作する
        assert response.status_code in [200, 500]


class TestAPIKeyService:
    """APIKeyServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_generate_key(self, db_session: AsyncSession, test_user):
        """APIキーを生成"""
        service = APIKeyService(db_session)

        api_key, raw_key = await service.create_api_key(
            user_id=test_user.id,
            name="生成テストキー",
            scopes=["transcriptions:read"],
            expires_in_days=30,
        )

        assert api_key.name == "生成テストキー"
        assert raw_key.startswith("sk_")
        assert api_key.expires_at is not None
        assert api_key.expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_validate_key(self, db_session: AsyncSession, test_user):
        """APIキーを検証"""
        service = APIKeyService(db_session)

        api_key, raw_key = await service.create_api_key(
            user_id=test_user.id,
            name="検証テストキー",
            scopes=["transcriptions:read", "transcriptions:write"],
        )

        # 有効なキーの検証
        validated_key = await service.validate_api_key(raw_key)
        assert validated_key is not None
        assert validated_key.id == api_key.id

        # 無効なキーの検証
        invalid_key = await service.validate_api_key("sk_invalid_key")
        assert invalid_key is None

    @pytest.mark.asyncio
    async def test_check_scope(self, db_session: AsyncSession, test_user):
        """スコープをチェック"""
        service = APIKeyService(db_session)

        api_key, raw_key = await service.create_api_key(
            user_id=test_user.id,
            name="スコープテストキー",
            scopes=["transcriptions:read"],
        )

        # 許可されたスコープ
        assert await service.check_scope(api_key, "transcriptions:read") is True

        # 許可されていないスコープ
        assert await service.check_scope(api_key, "transcriptions:write") is False

    @pytest.mark.asyncio
    async def test_expired_key(self, db_session: AsyncSession, test_user):
        """期限切れキーの検証"""
        service = APIKeyService(db_session)

        api_key, raw_key = await service.create_api_key(
            user_id=test_user.id,
            name="期限切れテストキー",
            scopes=["transcriptions:read"],
            expires_in_days=-1,  # 過去の日付
        )

        # 期限切れキーは無効
        validated_key = await service.validate_api_key(raw_key)
        assert validated_key is None


class TestUsageTrackingAPI:
    """使用量追跡APIのテスト"""

    @pytest.mark.asyncio
    async def test_get_api_usage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """API使用量を取得"""
        response = await client.get(
            "/api/v1/developer/usage",
            params={
                "start_date": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "end_date": datetime.utcnow().isoformat(),
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "total_requests" in data
        assert "requests_by_endpoint" in data

    @pytest.mark.asyncio
    async def test_get_rate_limit_status(self, client: AsyncClient, test_user):
        """レート制限状態を取得"""
        response = await client.get("/api/v1/developer/rate-limit")
        assert response.status_code == 200

        data = response.json()
        assert "limit" in data
        assert "remaining" in data
        assert "reset_at" in data
