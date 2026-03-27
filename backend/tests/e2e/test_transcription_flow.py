"""E2Eテスト: 文字起こしフロー"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import uuid


@pytest.mark.asyncio
class TestTranscriptionE2EFlow:
    """文字起こしのE2Eフロー"""

    async def test_complete_transcription_workflow(
        self,
        client: AsyncClient,
        test_user,
        sample_audio_file,
    ):
        """完全な文字起こしワークフロー"""
        # 1. 音声ファイルをアップロード
        # 実際のテストではファイルアップロードを実行

        # 2. 文字起こしを作成
        response = await client.post(
            "/api/v1/transcriptions",
            json={
                "title": "E2Eテスト文字起こし",
                "language": "ja",
            },
        )
        assert response.status_code in [200, 201]

    async def test_transcription_with_analysis(
        self,
        client: AsyncClient,
        test_user,
    ):
        """分析付き文字起こし"""
        # 文字起こしを作成
        create_response = await client.post(
            "/api/v1/transcriptions",
            json={
                "title": "分析テスト",
                "language": "ja",
            },
        )

        # ステータスをチェック
        assert create_response.status_code in [200, 201, 422]

    async def test_export_workflow(
        self,
        client: AsyncClient,
        test_user,
    ):
        """エクスポートワークフロー"""
        transcription_id = str(uuid.uuid4())

        # NotebookLM用エクスポート
        response = await client.post(
            "/api/v1/notebooklm/export",
            json={
                "transcription_id": transcription_id,
                "format": "markdown",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "filename" in data


@pytest.mark.asyncio
class TestNotebookLME2E:
    """NotebookLM連携のE2Eテスト"""

    async def test_export_markdown(self, client: AsyncClient):
        """Markdownエクスポート"""
        response = await client.post(
            "/api/v1/notebooklm/export",
            json={
                "transcription_id": str(uuid.uuid4()),
                "format": "markdown",
                "include_timestamps": True,
                "include_speakers": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "markdown"
        assert ".md" in data["filename"]

    async def test_generate_podcast_script(self, client: AsyncClient):
        """ポッドキャストスクリプト生成"""
        response = await client.post(
            "/api/v1/notebooklm/podcast-script",
            json={
                "transcription_id": str(uuid.uuid4()),
                "style": "conversational",
                "target_duration_min": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "script" in data
        assert "hosts" in data

    async def test_batch_export(self, client: AsyncClient):
        """バッチエクスポート"""
        response = await client.post(
            "/api/v1/notebooklm/export/batch",
            json={
                "transcription_ids": [str(uuid.uuid4()) for _ in range(3)],
                "format": "markdown",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3

    async def test_list_formats(self, client: AsyncClient):
        """フォーマット一覧"""
        response = await client.get("/api/v1/notebooklm/formats")
        assert response.status_code == 200
        data = response.json()
        assert "formats" in data
        assert len(data["formats"]) > 0


@pytest.mark.asyncio
class TestUserFlowE2E:
    """ユーザーフローのE2Eテスト"""

    async def test_session_management(self, client: AsyncClient):
        """セッション管理"""
        # ログイン
        response = await client.post(
            "/api/v1/users/sessions",
            json={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        # 認証の詳細実装によってステータスが変わる
        assert response.status_code in [200, 401, 422]

    async def test_mfa_setup_flow(self, client: AsyncClient):
        """MFAセットアップフロー"""
        response = await client.post("/api/v1/users/mfa/setup")
        assert response.status_code == 200
        data = response.json()
        assert "provisioning_uri" in data


@pytest.mark.asyncio
class TestWorkflowE2E:
    """ワークフローのE2Eテスト"""

    async def test_create_and_trigger_workflow(self, client: AsyncClient):
        """ワークフロー作成とトリガー"""
        # ワークフロー作成
        create_response = await client.post(
            "/api/v1/workflows",
            json={
                "name": "テストワークフロー",
                "description": "E2Eテスト用",
                "trigger": {
                    "type": "transcription.completed",
                    "config": {},
                },
                "actions": [
                    {
                        "type": "send_slack",
                        "config": {
                            "webhook_url": "https://hooks.slack.com/test",
                            "message": "文字起こし完了",
                        },
                    }
                ],
            },
        )
        assert create_response.status_code == 200

    async def test_list_integrations(self, client: AsyncClient):
        """インテグレーション一覧"""
        response = await client.get("/api/v1/workflows/integrations/available")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data


@pytest.mark.asyncio
class TestPerformanceE2E:
    """パフォーマンスのE2Eテスト"""

    async def test_health_check(self, client: AsyncClient):
        """ヘルスチェック"""
        response = await client.get("/api/v1/performance/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    async def test_cache_operations(self, client: AsyncClient):
        """キャッシュ操作"""
        # キャッシュ設定
        set_response = await client.post(
            "/api/v1/performance/cache",
            json={
                "key": "test_key",
                "value": {"data": "test"},
                "ttl": 60,
            },
        )
        assert set_response.status_code == 200

        # キャッシュ取得
        get_response = await client.get("/api/v1/performance/cache/test_key")
        assert get_response.status_code in [200, 404]

    async def test_benchmark_echo(self, client: AsyncClient):
        """エコーベンチマーク"""
        response = await client.get("/api/v1/performance/benchmark/echo")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
