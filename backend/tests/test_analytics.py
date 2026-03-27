import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
import uuid

from app.models.transcription import Transcription
from app.models.analytics import UsageMetrics
from app.services.analytics_service import AnalyticsService


class TestUsageAPI:
    """使用量APIのテスト"""

    @pytest.mark.asyncio
    async def test_get_usage_summary(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """使用量サマリーを取得"""
        # テストデータを作成
        metrics = UsageMetrics(
            user_id=test_user.id,
            date=date.today(),
            transcriptions_count=5,
            total_audio_duration_sec=3600,
            total_characters=10000,
            total_words=2000,
            api_calls_count=50,
        )
        db_session.add(metrics)
        await db_session.commit()

        response = await client.get("/api/v1/analytics/usage/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["total_transcriptions"] == 5
        assert data["total_duration_sec"] == 3600
        assert data["total_words"] == 2000

    @pytest.mark.asyncio
    async def test_get_usage_trend(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """使用量トレンドを取得"""
        # 過去7日間のデータを作成
        for i in range(7):
            metrics = UsageMetrics(
                user_id=test_user.id,
                date=date.today() - timedelta(days=i),
                transcriptions_count=i + 1,
                total_audio_duration_sec=(i + 1) * 600,
                total_words=(i + 1) * 500,
            )
            db_session.add(metrics)
        await db_session.commit()

        response = await client.get(
            "/api/v1/analytics/usage/trend",
            params={
                "start_date": (date.today() - timedelta(days=6)).isoformat(),
                "end_date": date.today().isoformat(),
                "group_by": "day",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 7


class TestTranscriptionAnalyticsAPI:
    """文字起こし分析APIのテスト"""

    @pytest.mark.asyncio
    async def test_analyze_transcription(
        self,
        client: AsyncClient,
        test_transcription_with_segments,
    ):
        """文字起こしを分析"""
        response = await client.post(
            f"/api/v1/analytics/transcriptions/{test_transcription_with_segments.id}/analyze"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total_segments"] == 3
        assert data["speaker_count"] == 2
        assert "keywords" in data
        assert "speaking_rate_wpm" in data

    @pytest.mark.asyncio
    async def test_get_transcription_analytics(
        self,
        client: AsyncClient,
        test_transcription_with_segments,
    ):
        """分析結果を取得"""
        # まず分析を実行
        await client.post(
            f"/api/v1/analytics/transcriptions/{test_transcription_with_segments.id}/analyze"
        )

        # 結果を取得
        response = await client.get(
            f"/api/v1/analytics/transcriptions/{test_transcription_with_segments.id}/analytics"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["transcription_id"] == str(test_transcription_with_segments.id)


class TestReportAPI:
    """レポートAPIのテスト"""

    @pytest.mark.asyncio
    async def test_create_report(self, client: AsyncClient, test_user):
        """レポートを作成"""
        response = await client.post(
            "/api/v1/analytics/reports",
            json={
                "name": "月次使用量レポート",
                "report_type": "usage",
                "config": {
                    "start_date": (date.today() - timedelta(days=30)).isoformat(),
                    "end_date": date.today().isoformat(),
                    "group_by": "week",
                },
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "月次使用量レポート"
        assert data["report_type"] == "usage"

    @pytest.mark.asyncio
    async def test_list_reports(self, client: AsyncClient, test_user):
        """レポート一覧を取得"""
        # レポートを作成
        await client.post(
            "/api/v1/analytics/reports",
            json={
                "name": "レポート1",
                "report_type": "usage",
                "config": {},
            },
        )
        await client.post(
            "/api/v1/analytics/reports",
            json={
                "name": "レポート2",
                "report_type": "transcription",
                "config": {},
            },
        )

        response = await client.get("/api/v1/analytics/reports")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2


class TestDashboardAPI:
    """ダッシュボードAPIのテスト"""

    @pytest.mark.asyncio
    async def test_get_dashboard(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        test_transcription,
    ):
        """ダッシュボードを取得"""
        # 使用量データを追加
        metrics = UsageMetrics(
            user_id=test_user.id,
            date=date.today(),
            transcriptions_count=10,
            total_audio_duration_sec=7200,
        )
        db_session.add(metrics)
        await db_session.commit()

        response = await client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert "monthly_usage" in data
        assert "weekly_trend" in data
        assert "recent_transcriptions" in data
        assert "top_speakers" in data


class TestAnalyticsService:
    """AnalyticsServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_increment_metrics(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """メトリクスの増加"""
        service = AnalyticsService(db_session)

        # 初回
        metrics = await service.increment_metrics(
            user_id=test_user.id,
            transcriptions=1,
            audio_duration_sec=300,
            words=500,
        )
        assert metrics.transcriptions_count == 1
        assert metrics.total_audio_duration_sec == 300

        # 2回目（累積）
        metrics = await service.increment_metrics(
            user_id=test_user.id,
            transcriptions=2,
            audio_duration_sec=600,
            words=1000,
        )
        assert metrics.transcriptions_count == 3
        assert metrics.total_audio_duration_sec == 900

    @pytest.mark.asyncio
    async def test_analyze_transcription(
        self,
        db_session: AsyncSession,
        test_transcription_with_segments,
    ):
        """文字起こし分析"""
        service = AnalyticsService(db_session)

        analytics = await service.analyze_transcription(
            test_transcription_with_segments.id
        )

        assert analytics.total_segments == 3
        assert analytics.speaker_count == 2
        assert analytics.total_words > 0
        assert analytics.keywords is not None
