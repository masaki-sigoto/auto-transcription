"""高度な分析・インサイトサービス"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID
from dataclasses import dataclass
from enum import Enum
import json
from collections import defaultdict
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx

from app.core.config import get_settings

settings = get_settings()


class TrendPeriod(str, Enum):
    """トレンド期間"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass
class MeetingTrend:
    """会議トレンド"""
    period: str
    total_meetings: int
    total_duration_minutes: int
    avg_duration_minutes: float
    total_participants: int
    avg_participants: float
    top_topics: List[str]
    sentiment_trend: Dict[str, float]


@dataclass
class SpeakerAnalysis:
    """話者分析"""
    speaker_id: str
    speaker_name: str
    total_speaking_time_seconds: float
    speaking_percentage: float
    word_count: int
    avg_words_per_minute: float
    sentiment_distribution: Dict[str, float]
    top_keywords: List[str]
    interaction_score: float  # 他者との対話度


@dataclass
class TeamProductivity:
    """チーム生産性"""
    team_id: str
    team_name: str
    period: str
    total_meetings: int
    total_meeting_hours: float
    action_items_created: int
    action_items_completed: int
    completion_rate: float
    avg_meeting_effectiveness: float  # 0-100
    meeting_cost_estimate: float  # 概算コスト
    recommendations: List[str]


@dataclass
class MeetingInsight:
    """会議インサイト"""
    insight_type: str  # efficiency, participation, topic, action
    title: str
    description: str
    severity: str  # info, warning, critical
    data: Dict[str, Any]
    recommendations: List[str]


class AdvancedAnalyticsService:
    """高度な分析サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_meeting_trends(
        self,
        user_id: UUID,
        team_id: Optional[UUID] = None,
        period: TrendPeriod = TrendPeriod.WEEKLY,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[MeetingTrend]:
        """会議トレンドを取得"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            if period == TrendPeriod.DAILY:
                start_date = end_date - timedelta(days=30)
            elif period == TrendPeriod.WEEKLY:
                start_date = end_date - timedelta(weeks=12)
            elif period == TrendPeriod.MONTHLY:
                start_date = end_date - timedelta(days=365)
            else:
                start_date = end_date - timedelta(days=730)

        # 期間ごとのグループ化
        if period == TrendPeriod.DAILY:
            date_trunc = "day"
        elif period == TrendPeriod.WEEKLY:
            date_trunc = "week"
        elif period == TrendPeriod.MONTHLY:
            date_trunc = "month"
        else:
            date_trunc = "quarter"

        query = f"""
            SELECT
                DATE_TRUNC(:date_trunc, created_at) as period,
                COUNT(*) as total_meetings,
                SUM(audio_duration_sec) / 60 as total_duration_minutes,
                AVG(audio_duration_sec) / 60 as avg_duration_minutes
            FROM transcriptions
            WHERE created_at BETWEEN :start_date AND :end_date
        """

        params: Dict[str, Any] = {
            "date_trunc": date_trunc,
            "start_date": start_date,
            "end_date": end_date,
        }

        if team_id:
            query += " AND team_id = :team_id"
            params["team_id"] = str(team_id)

        query += " GROUP BY DATE_TRUNC(:date_trunc, created_at) ORDER BY period"

        result = await self.db.execute(text(query), params)
        rows = result.fetchall()

        trends = []
        for row in rows:
            trends.append(MeetingTrend(
                period=row[0].isoformat() if row[0] else "",
                total_meetings=row[1] or 0,
                total_duration_minutes=int(row[2] or 0),
                avg_duration_minutes=float(row[3] or 0),
                total_participants=0,  # 別途計算
                avg_participants=0,
                top_topics=[],
                sentiment_trend={},
            ))

        return trends

    async def analyze_speaker(
        self,
        transcription_id: UUID,
    ) -> List[SpeakerAnalysis]:
        """話者分析を実行"""
        # セグメントを取得
        result = await self.db.execute(
            text("""
                SELECT
                    speaker_label,
                    SUM(end_time_ms - start_time_ms) / 1000.0 as speaking_time,
                    STRING_AGG(text, ' ') as all_text
                FROM segments
                WHERE transcription_id = :id AND speaker_label IS NOT NULL
                GROUP BY speaker_label
            """),
            {"id": str(transcription_id)},
        )
        rows = result.fetchall()

        # 総発言時間
        total_time = sum(row[1] or 0 for row in rows)

        analyses = []
        for row in rows:
            speaker_label = row[0]
            speaking_time = row[1] or 0
            all_text = row[2] or ""

            word_count = len(all_text.split())
            wpm = (word_count / (speaking_time / 60)) if speaking_time > 0 else 0

            # キーワード抽出（簡易版）
            top_keywords = await self._extract_keywords(all_text, limit=5)

            # 感情分析（簡易版）
            sentiment = await self._analyze_sentiment_simple(all_text)

            analyses.append(SpeakerAnalysis(
                speaker_id=speaker_label,
                speaker_name=speaker_label,
                total_speaking_time_seconds=speaking_time,
                speaking_percentage=(speaking_time / total_time * 100) if total_time > 0 else 0,
                word_count=word_count,
                avg_words_per_minute=wpm,
                sentiment_distribution=sentiment,
                top_keywords=top_keywords,
                interaction_score=0,  # 別途計算
            ))

        return analyses

    async def _extract_keywords(self, text: str, limit: int = 5) -> List[str]:
        """キーワード抽出（簡易版）"""
        # 実際の実装では形態素解析やTF-IDFを使用
        words = text.split()
        word_freq = defaultdict(int)
        for word in words:
            if len(word) > 2:  # 3文字以上
                word_freq[word] += 1

        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w[0] for w in sorted_words[:limit]]

    async def _analyze_sentiment_simple(self, text: str) -> Dict[str, float]:
        """簡易感情分析"""
        # 実際の実装ではMLモデルを使用
        positive_words = ["良い", "素晴らしい", "嬉しい", "ありがとう", "成功", "達成"]
        negative_words = ["悪い", "問題", "課題", "困難", "失敗", "遅延"]

        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        total = positive_count + negative_count + 1

        return {
            "positive": positive_count / total,
            "negative": negative_count / total,
            "neutral": 1 - (positive_count + negative_count) / total,
        }

    async def get_team_productivity(
        self,
        team_id: UUID,
        period: TrendPeriod = TrendPeriod.MONTHLY,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> TeamProductivity:
        """チーム生産性を計算"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # 会議統計
        result = await self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_meetings,
                    SUM(audio_duration_sec) / 3600.0 as total_hours
                FROM transcriptions
                WHERE team_id = :team_id
                AND created_at BETWEEN :start_date AND :end_date
            """),
            {
                "team_id": str(team_id),
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        row = result.fetchone()
        total_meetings = row[0] or 0
        total_hours = float(row[1] or 0)

        # アクションアイテム統計（ai_analysisから）
        action_result = await self.db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'created') as created,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed
                FROM action_items
                WHERE team_id = :team_id
                AND created_at BETWEEN :start_date AND :end_date
            """),
            {
                "team_id": str(team_id),
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        action_row = action_result.fetchone()
        action_items_created = action_row[0] if action_row else 0
        action_items_completed = action_row[1] if action_row else 0

        completion_rate = (action_items_completed / action_items_created * 100) if action_items_created > 0 else 0

        # 会議効率スコア計算
        effectiveness = self._calculate_effectiveness(
            total_meetings,
            total_hours,
            completion_rate,
        )

        # コスト概算（1時間あたり5000円として）
        hourly_rate = 5000
        meeting_cost = total_hours * hourly_rate * 2  # 平均2人参加と仮定

        # 推奨事項
        recommendations = self._generate_productivity_recommendations(
            total_meetings,
            total_hours,
            completion_rate,
            effectiveness,
        )

        # チーム名を取得
        team_result = await self.db.execute(
            text("SELECT name FROM teams WHERE id = :id"),
            {"id": str(team_id)},
        )
        team_row = team_result.fetchone()
        team_name = team_row[0] if team_row else "Unknown"

        return TeamProductivity(
            team_id=str(team_id),
            team_name=team_name,
            period=f"{start_date.date()} - {end_date.date()}",
            total_meetings=total_meetings,
            total_meeting_hours=total_hours,
            action_items_created=action_items_created,
            action_items_completed=action_items_completed,
            completion_rate=completion_rate,
            avg_meeting_effectiveness=effectiveness,
            meeting_cost_estimate=meeting_cost,
            recommendations=recommendations,
        )

    def _calculate_effectiveness(
        self,
        total_meetings: int,
        total_hours: float,
        completion_rate: float,
    ) -> float:
        """会議効率スコアを計算"""
        if total_meetings == 0:
            return 0

        avg_duration = (total_hours / total_meetings) * 60  # 分

        # 理想的な会議時間は30-45分
        duration_score = 100 - abs(37.5 - avg_duration) * 2
        duration_score = max(0, min(100, duration_score))

        # 完了率スコア
        completion_score = completion_rate

        # 総合スコア
        effectiveness = (duration_score * 0.4 + completion_score * 0.6)

        return round(effectiveness, 1)

    def _generate_productivity_recommendations(
        self,
        total_meetings: int,
        total_hours: float,
        completion_rate: float,
        effectiveness: float,
    ) -> List[str]:
        """生産性向上の推奨事項を生成"""
        recommendations = []

        if total_meetings > 0:
            avg_duration = (total_hours / total_meetings) * 60

            if avg_duration > 60:
                recommendations.append("会議時間が長い傾向があります。45分以内に収めることを検討してください。")

            if avg_duration < 15:
                recommendations.append("会議時間が短すぎる可能性があります。十分な議論時間を確保してください。")

        if completion_rate < 50:
            recommendations.append("アクションアイテムの完了率が低いです。タスク管理を強化してください。")

        if effectiveness < 50:
            recommendations.append("会議の効率化が必要です。アジェンダの事前共有を検討してください。")

        if total_meetings > 20:
            recommendations.append("会議数が多いです。非同期コミュニケーションの活用を検討してください。")

        if not recommendations:
            recommendations.append("良好なパフォーマンスを維持しています。")

        return recommendations

    async def generate_insights(
        self,
        transcription_id: UUID,
    ) -> List[MeetingInsight]:
        """会議インサイトを生成"""
        insights = []

        # 文字起こしを取得
        result = await self.db.execute(
            text("""
                SELECT title, audio_duration_sec, full_text, created_at
                FROM transcriptions
                WHERE id = :id
            """),
            {"id": str(transcription_id)},
        )
        row = result.fetchone()

        if not row:
            return insights

        title, duration_sec, full_text, created_at = row
        duration_min = (duration_sec or 0) / 60

        # 会議時間インサイト
        if duration_min > 60:
            insights.append(MeetingInsight(
                insight_type="efficiency",
                title="会議時間が長い",
                description=f"この会議は{int(duration_min)}分です。効率化の余地があるかもしれません。",
                severity="warning",
                data={"duration_minutes": duration_min},
                recommendations=[
                    "アジェンダを事前に共有する",
                    "タイムキーパーを設定する",
                    "議論が長引く場合は別途ミーティングを設定する",
                ],
            ))

        # 話者分析インサイト
        speaker_analyses = await self.analyze_speaker(transcription_id)

        if speaker_analyses:
            # 発言偏りチェック
            max_percentage = max(s.speaking_percentage for s in speaker_analyses)
            if max_percentage > 70 and len(speaker_analyses) > 1:
                dominant_speaker = next(s for s in speaker_analyses if s.speaking_percentage == max_percentage)
                insights.append(MeetingInsight(
                    insight_type="participation",
                    title="発言の偏り",
                    description=f"{dominant_speaker.speaker_name}の発言が{int(max_percentage)}%を占めています。",
                    severity="info",
                    data={
                        "dominant_speaker": dominant_speaker.speaker_name,
                        "percentage": max_percentage,
                    },
                    recommendations=[
                        "全員に発言機会を設ける",
                        "質問形式で意見を求める",
                        "事前にアイデアを共有してもらう",
                    ],
                ))

        return insights


class ReportService:
    """レポート生成サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analytics = AdvancedAnalyticsService(db)

    async def generate_summary_report(
        self,
        user_id: UUID,
        team_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "json",
    ) -> Dict[str, Any]:
        """サマリーレポートを生成"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # トレンドデータ
        trends = await self.analytics.get_meeting_trends(
            user_id=user_id,
            team_id=team_id,
            period=TrendPeriod.WEEKLY,
            start_date=start_date,
            end_date=end_date,
        )

        # チーム生産性
        productivity = None
        if team_id:
            productivity = await self.analytics.get_team_productivity(
                team_id=team_id,
                start_date=start_date,
                end_date=end_date,
            )

        report = {
            "report_type": "summary",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "trends": [
                {
                    "period": t.period,
                    "total_meetings": t.total_meetings,
                    "total_duration_minutes": t.total_duration_minutes,
                    "avg_duration_minutes": t.avg_duration_minutes,
                }
                for t in trends
            ],
            "productivity": {
                "total_meetings": productivity.total_meetings if productivity else 0,
                "total_hours": productivity.total_meeting_hours if productivity else 0,
                "action_items_completion_rate": productivity.completion_rate if productivity else 0,
                "effectiveness_score": productivity.avg_meeting_effectiveness if productivity else 0,
                "recommendations": productivity.recommendations if productivity else [],
            } if productivity else None,
        }

        return report

    async def export_to_excel(
        self,
        report_data: Dict[str, Any],
    ) -> bytes:
        """Excelファイルとしてエクスポート"""
        import io
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Summary"

        # ヘッダー
        ws.append(["期間", report_data["period"]["start"], "-", report_data["period"]["end"]])
        ws.append([])

        # トレンドデータ
        ws.append(["週", "会議数", "総時間（分）", "平均時間（分）"])
        for trend in report_data.get("trends", []):
            ws.append([
                trend["period"],
                trend["total_meetings"],
                trend["total_duration_minutes"],
                round(trend["avg_duration_minutes"], 1),
            ])

        # 生産性データ
        if report_data.get("productivity"):
            ws.append([])
            ws.append(["生産性指標"])
            prod = report_data["productivity"]
            ws.append(["総会議数", prod["total_meetings"]])
            ws.append(["総会議時間（時間）", round(prod["total_hours"], 1)])
            ws.append(["アクションアイテム完了率", f"{prod['action_items_completion_rate']:.1f}%"])
            ws.append(["効率スコア", f"{prod['effectiveness_score']:.1f}"])

        # バイト列として返す
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return output.getvalue()

    async def export_to_pdf(
        self,
        report_data: Dict[str, Any],
    ) -> bytes:
        """PDFファイルとしてエクスポート"""
        # 実際の実装ではreportlab等を使用
        # ここでは簡易的にJSON文字列を返す
        import io

        content = json.dumps(report_data, ensure_ascii=False, indent=2)
        return content.encode("utf-8")
