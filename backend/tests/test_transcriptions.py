import pytest
from httpx import AsyncClient
import uuid

from app.models.transcription import Transcription


class TestTranscriptionAPI:
    """文字起こしAPIのテスト"""

    @pytest.mark.asyncio
    async def test_list_transcriptions_empty(self, client: AsyncClient):
        """空の文字起こし一覧を取得"""
        response = await client.get("/api/v1/transcriptions")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_transcriptions(
        self,
        client: AsyncClient,
        test_transcription: Transcription,
    ):
        """文字起こし一覧を取得"""
        response = await client.get("/api/v1/transcriptions")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "テスト文字起こし"
        assert data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_transcription(
        self,
        client: AsyncClient,
        test_transcription: Transcription,
    ):
        """文字起こし詳細を取得"""
        response = await client.get(f"/api/v1/transcriptions/{test_transcription.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(test_transcription.id)
        assert data["title"] == "テスト文字起こし"
        assert data["audio_duration_sec"] == 120

    @pytest.mark.asyncio
    async def test_get_transcription_not_found(self, client: AsyncClient):
        """存在しない文字起こしを取得"""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/transcriptions/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_transcription(
        self,
        client: AsyncClient,
        test_transcription: Transcription,
    ):
        """文字起こしを更新"""
        response = await client.patch(
            f"/api/v1/transcriptions/{test_transcription.id}",
            json={"title": "更新されたタイトル"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["title"] == "更新されたタイトル"

    @pytest.mark.asyncio
    async def test_delete_transcription(
        self,
        client: AsyncClient,
        test_transcription: Transcription,
    ):
        """文字起こしを削除"""
        response = await client.delete(f"/api/v1/transcriptions/{test_transcription.id}")
        assert response.status_code == 204

        # 削除されたことを確認
        response = await client.get(f"/api/v1/transcriptions/{test_transcription.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_transcription_with_segments(
        self,
        client: AsyncClient,
        test_transcription_with_segments: Transcription,
    ):
        """セグメント付きの文字起こしを取得"""
        response = await client.get(
            f"/api/v1/transcriptions/{test_transcription_with_segments.id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["segments"]) == 3
        assert data["segments"][0]["text"] == "こんにちは、本日はよろしくお願いします。"


class TestTranscriptionExport:
    """エクスポート機能のテスト"""

    @pytest.mark.asyncio
    async def test_export_srt(
        self,
        client: AsyncClient,
        test_transcription_with_segments: Transcription,
    ):
        """SRT形式でエクスポート"""
        response = await client.get(
            f"/api/v1/transcriptions/{test_transcription_with_segments.id}/export",
            params={"format": "srt"},
        )
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        content = response.text
        assert "00:00:00,000 --> 00:00:05,000" in content
        assert "こんにちは、本日はよろしくお願いします。" in content

    @pytest.mark.asyncio
    async def test_export_vtt(
        self,
        client: AsyncClient,
        test_transcription_with_segments: Transcription,
    ):
        """VTT形式でエクスポート"""
        response = await client.get(
            f"/api/v1/transcriptions/{test_transcription_with_segments.id}/export",
            params={"format": "vtt"},
        )
        assert response.status_code == 200

        content = response.text
        assert "WEBVTT" in content
        assert "00:00:00.000 --> 00:00:05.000" in content

    @pytest.mark.asyncio
    async def test_export_json(
        self,
        client: AsyncClient,
        test_transcription_with_segments: Transcription,
    ):
        """JSON形式でエクスポート"""
        response = await client.get(
            f"/api/v1/transcriptions/{test_transcription_with_segments.id}/export",
            params={"format": "json"},
        )
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert "title" in data
        assert "segments" in data
        assert len(data["segments"]) == 3


class TestTranscriptionSearch:
    """検索機能のテスト"""

    @pytest.mark.asyncio
    async def test_search_transcriptions(
        self,
        client: AsyncClient,
        test_transcription_with_segments: Transcription,
    ):
        """文字起こしを検索"""
        response = await client.get(
            f"/api/v1/transcriptions/{test_transcription_with_segments.id}/search",
            params={"query": "よろしく"},
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        # 検索結果に「よろしく」を含むセグメントがある
        assert any("よろしく" in result["text"] for result in data)
