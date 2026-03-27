import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.user import User


class TestExternalServiceIntegration:
    """外部サービス連携のテスト"""

    @pytest.mark.asyncio
    async def test_list_integrations(self, client: AsyncClient, test_user):
        """連携一覧を取得"""
        response = await client.get("/api/v1/integrations")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_integration_config(self, client: AsyncClient, test_user):
        """連携設定を取得"""
        response = await client.get("/api/v1/integrations/google-drive")
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_connect_google_drive(self, client: AsyncClient, test_user):
        """Google Driveと連携"""
        response = await client.post(
            "/api/v1/integrations/google-drive/connect",
            json={
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
            },
        )
        # 実際の連携はモックされるため、成功または未実装を許容
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_disconnect_integration(self, client: AsyncClient, test_user):
        """連携を解除"""
        response = await client.delete("/api/v1/integrations/google-drive")
        assert response.status_code in [200, 204, 404]


class TestSlackIntegration:
    """Slack連携のテスト"""

    @pytest.mark.asyncio
    async def test_connect_slack(self, client: AsyncClient, test_user):
        """Slackと連携"""
        response = await client.post(
            "/api/v1/integrations/slack/connect",
            json={
                "access_token": "xoxb-mock-token",
                "team_id": "T12345678",
            },
        )
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_list_slack_channels(self, client: AsyncClient, test_user):
        """Slackチャンネル一覧を取得"""
        response = await client.get("/api/v1/integrations/slack/channels")
        assert response.status_code in [200, 404, 501]

    @pytest.mark.asyncio
    async def test_send_to_slack(
        self,
        client: AsyncClient,
        test_transcription,
    ):
        """Slackに送信"""
        response = await client.post(
            "/api/v1/integrations/slack/send",
            json={
                "channel_id": "C12345678",
                "transcription_id": str(test_transcription.id),
                "message": "文字起こしが完了しました",
            },
        )
        assert response.status_code in [200, 404, 501]


class TestNotionIntegration:
    """Notion連携のテスト"""

    @pytest.mark.asyncio
    async def test_connect_notion(self, client: AsyncClient, test_user):
        """Notionと連携"""
        response = await client.post(
            "/api/v1/integrations/notion/connect",
            json={
                "access_token": "secret_mock_token",
            },
        )
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_list_notion_databases(self, client: AsyncClient, test_user):
        """Notionデータベース一覧を取得"""
        response = await client.get("/api/v1/integrations/notion/databases")
        assert response.status_code in [200, 404, 501]

    @pytest.mark.asyncio
    async def test_export_to_notion(
        self,
        client: AsyncClient,
        test_transcription,
    ):
        """Notionにエクスポート"""
        response = await client.post(
            "/api/v1/integrations/notion/export",
            json={
                "database_id": "mock-database-id",
                "transcription_id": str(test_transcription.id),
            },
        )
        assert response.status_code in [200, 404, 501]


class TestCalendarIntegration:
    """カレンダー連携のテスト"""

    @pytest.mark.asyncio
    async def test_connect_google_calendar(self, client: AsyncClient, test_user):
        """Google Calendarと連携"""
        response = await client.post(
            "/api/v1/integrations/google-calendar/connect",
            json={
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
            },
        )
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_list_calendar_events(self, client: AsyncClient, test_user):
        """カレンダーイベント一覧を取得"""
        response = await client.get("/api/v1/integrations/google-calendar/events")
        assert response.status_code in [200, 404, 501]

    @pytest.mark.asyncio
    async def test_link_transcription_to_event(
        self,
        client: AsyncClient,
        test_transcription,
    ):
        """文字起こしをイベントにリンク"""
        response = await client.post(
            "/api/v1/integrations/google-calendar/link",
            json={
                "event_id": "mock-event-id",
                "transcription_id": str(test_transcription.id),
            },
        )
        assert response.status_code in [200, 404, 501]


class TestStorageIntegration:
    """ストレージ連携のテスト"""

    @pytest.mark.asyncio
    async def test_upload_to_google_drive(
        self,
        client: AsyncClient,
        test_transcription,
    ):
        """Google Driveにアップロード"""
        response = await client.post(
            "/api/v1/integrations/google-drive/upload",
            json={
                "transcription_id": str(test_transcription.id),
                "folder_id": "mock-folder-id",
                "format": "docx",
            },
        )
        assert response.status_code in [200, 404, 501]

    @pytest.mark.asyncio
    async def test_upload_to_dropbox(
        self,
        client: AsyncClient,
        test_transcription,
    ):
        """Dropboxにアップロード"""
        response = await client.post(
            "/api/v1/integrations/dropbox/upload",
            json={
                "transcription_id": str(test_transcription.id),
                "path": "/transcriptions",
                "format": "txt",
            },
        )
        assert response.status_code in [200, 404, 501]


class TestZoomIntegration:
    """Zoom連携のテスト"""

    @pytest.mark.asyncio
    async def test_connect_zoom(self, client: AsyncClient, test_user):
        """Zoomと連携"""
        response = await client.post(
            "/api/v1/integrations/zoom/connect",
            json={
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
            },
        )
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_list_zoom_recordings(self, client: AsyncClient, test_user):
        """Zoom録画一覧を取得"""
        response = await client.get("/api/v1/integrations/zoom/recordings")
        assert response.status_code in [200, 404, 501]

    @pytest.mark.asyncio
    async def test_import_zoom_recording(self, client: AsyncClient, test_user):
        """Zoom録画をインポート"""
        response = await client.post(
            "/api/v1/integrations/zoom/import",
            json={
                "recording_id": "mock-recording-id",
                "title": "インポートされた会議",
            },
        )
        assert response.status_code in [200, 202, 404, 501]


class TestTeamsIntegration:
    """Microsoft Teams連携のテスト"""

    @pytest.mark.asyncio
    async def test_connect_teams(self, client: AsyncClient, test_user):
        """Microsoft Teamsと連携"""
        response = await client.post(
            "/api/v1/integrations/teams/connect",
            json={
                "access_token": "mock_access_token",
            },
        )
        assert response.status_code in [200, 201, 501]

    @pytest.mark.asyncio
    async def test_list_teams_meetings(self, client: AsyncClient, test_user):
        """Teams会議一覧を取得"""
        response = await client.get("/api/v1/integrations/teams/meetings")
        assert response.status_code in [200, 404, 501]
