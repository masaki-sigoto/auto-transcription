"""高度なレポート・ダッシュボードサービス"""

import os
import uuid
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from collections import defaultdict


class MetricType(str, Enum):
    TRANSCRIPTION_COUNT = "transcription_count"
    TOTAL_DURATION = "total_duration"
    WORD_COUNT = "word_count"
    SPEAKER_COUNT = "speaker_count"
    MEETING_COUNT = "meeting_count"
    ACTIVE_USERS = "active_users"


class TimeRange(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_YEAR = "this_year"
    CUSTOM = "custom"


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    DONUT = "donut"
    AREA = "area"
    SCATTER = "scatter"
    HEATMAP = "heatmap"


@dataclass
class DashboardMetric:
    """メトリック"""
    name: str
    value: float
    unit: str
    change_percent: Optional[float] = None
    change_direction: Optional[str] = None  # up, down, stable
    previous_value: Optional[float] = None


@dataclass
class TimeSeriesData:
    """時系列データ"""
    timestamps: List[datetime]
    values: List[float]
    label: str
    color: Optional[str] = None


@dataclass
class ChartData:
    """チャートデータ"""
    chart_type: ChartType
    title: str
    series: List[TimeSeriesData]
    x_axis_label: str
    y_axis_label: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpeakerStats:
    """話者統計"""
    speaker_id: str
    speaker_name: str
    total_speaking_time_sec: int
    word_count: int
    segment_count: int
    speaking_percentage: float
    avg_segment_duration_sec: float
    sentiment_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class MeetingStats:
    """会議統計"""
    meeting_id: str
    title: str
    date: datetime
    duration_sec: int
    participant_count: int
    word_count: int
    action_item_count: int
    sentiment_summary: Dict[str, float] = field(default_factory=dict)


@dataclass
class ProductivityReport:
    """生産性レポート"""
    period_start: datetime
    period_end: datetime
    total_meetings: int
    total_meeting_time_hours: float
    avg_meeting_duration_min: float
    action_items_created: int
    action_items_completed: int
    completion_rate: float
    most_active_days: List[str]
    peak_hours: List[int]


@dataclass
class TrendAnalysis:
    """トレンド分析"""
    metric: str
    current_value: float
    trend_direction: str  # increasing, decreasing, stable
    trend_percentage: float
    forecast_next_period: float
    seasonality_detected: bool
    anomalies: List[Dict[str, Any]]


class DashboardAnalyticsEngine:
    """ダッシュボード分析エンジン"""

    def __init__(self):
        self._transcription_data: Dict[str, List[Dict]] = {}
        self._meeting_data: Dict[str, List[Dict]] = {}
        self._user_activity: Dict[str, List[Dict]] = {}

    def _get_date_range(
        self,
        time_range: TimeRange,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[datetime, datetime]:
        """日付範囲を取得"""
        now = datetime.utcnow()

        if time_range == TimeRange.TODAY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif time_range == TimeRange.YESTERDAY:
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59)
        elif time_range == TimeRange.LAST_7_DAYS:
            start = now - timedelta(days=7)
            end = now
        elif time_range == TimeRange.LAST_30_DAYS:
            start = now - timedelta(days=30)
            end = now
        elif time_range == TimeRange.LAST_90_DAYS:
            start = now - timedelta(days=90)
            end = now
        elif time_range == TimeRange.THIS_MONTH:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif time_range == TimeRange.LAST_MONTH:
            first_of_month = now.replace(day=1)
            end = first_of_month - timedelta(days=1)
            start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif time_range == TimeRange.THIS_YEAR:
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif time_range == TimeRange.CUSTOM:
            start = start_date or now - timedelta(days=30)
            end = end_date or now
        else:
            start = now - timedelta(days=30)
            end = now

        return start, end

    async def get_overview_metrics(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> List[DashboardMetric]:
        """概要メトリクスを取得"""
        start, end = self._get_date_range(time_range)

        # シミュレーションデータ
        metrics = [
            DashboardMetric(
                name="文字起こし数",
                value=156,
                unit="件",
                change_percent=12.5,
                change_direction="up",
                previous_value=139,
            ),
            DashboardMetric(
                name="総録音時間",
                value=48.5,
                unit="時間",
                change_percent=8.3,
                change_direction="up",
                previous_value=44.8,
            ),
            DashboardMetric(
                name="アクティブユーザー",
                value=23,
                unit="人",
                change_percent=-2.1,
                change_direction="down",
                previous_value=24,
            ),
            DashboardMetric(
                name="総単語数",
                value=125000,
                unit="語",
                change_percent=15.2,
                change_direction="up",
                previous_value=108500,
            ),
            DashboardMetric(
                name="会議数",
                value=89,
                unit="件",
                change_percent=5.8,
                change_direction="up",
                previous_value=84,
            ),
            DashboardMetric(
                name="平均会議時間",
                value=32.5,
                unit="分",
                change_percent=-1.5,
                change_direction="down",
                previous_value=33.0,
            ),
        ]

        return metrics

    async def get_transcription_trend(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        granularity: str = "day",
    ) -> ChartData:
        """文字起こしトレンドを取得"""
        start, end = self._get_date_range(time_range)

        timestamps = []
        values = []

        current = start
        import random
        random.seed(42)

        while current <= end:
            timestamps.append(current)
            values.append(random.randint(3, 15))

            if granularity == "hour":
                current += timedelta(hours=1)
            elif granularity == "day":
                current += timedelta(days=1)
            elif granularity == "week":
                current += timedelta(weeks=1)
            else:
                current += timedelta(days=30)

        series = [
            TimeSeriesData(
                timestamps=timestamps,
                values=values,
                label="文字起こし数",
                color="#3B82F6",
            )
        ]

        return ChartData(
            chart_type=ChartType.LINE,
            title="文字起こしトレンド",
            series=series,
            x_axis_label="日付",
            y_axis_label="件数",
        )

    async def get_duration_distribution(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> ChartData:
        """録音時間分布を取得"""
        categories = ["0-5分", "5-15分", "15-30分", "30-60分", "60分以上"]
        values = [25, 45, 55, 28, 12]

        series = [
            TimeSeriesData(
                timestamps=[datetime.utcnow()] * len(categories),
                values=values,
                label="録音数",
                color="#10B981",
            )
        ]

        return ChartData(
            chart_type=ChartType.BAR,
            title="録音時間分布",
            series=series,
            x_axis_label="時間帯",
            y_axis_label="件数",
            metadata={"categories": categories},
        )

    async def get_speaker_analytics(
        self,
        tenant_id: str,
        transcription_id: Optional[str] = None,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> List[SpeakerStats]:
        """話者分析を取得"""
        speakers = [
            SpeakerStats(
                speaker_id="spk_1",
                speaker_name="田中太郎",
                total_speaking_time_sec=3600,
                word_count=4500,
                segment_count=120,
                speaking_percentage=35.5,
                avg_segment_duration_sec=30.0,
                sentiment_scores={"positive": 0.6, "neutral": 0.3, "negative": 0.1},
            ),
            SpeakerStats(
                speaker_id="spk_2",
                speaker_name="佐藤花子",
                total_speaking_time_sec=2800,
                word_count=3200,
                segment_count=95,
                speaking_percentage=27.8,
                avg_segment_duration_sec=29.5,
                sentiment_scores={"positive": 0.5, "neutral": 0.4, "negative": 0.1},
            ),
            SpeakerStats(
                speaker_id="spk_3",
                speaker_name="鈴木一郎",
                total_speaking_time_sec=2200,
                word_count=2800,
                segment_count=75,
                speaking_percentage=21.8,
                avg_segment_duration_sec=29.3,
                sentiment_scores={"positive": 0.4, "neutral": 0.5, "negative": 0.1},
            ),
        ]

        return speakers

    async def get_meeting_statistics(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> List[MeetingStats]:
        """会議統計を取得"""
        start, end = self._get_date_range(time_range)

        meetings = []
        import random
        random.seed(123)

        for i in range(10):
            meeting_date = start + timedelta(days=random.randint(0, (end - start).days))
            meetings.append(MeetingStats(
                meeting_id=f"meeting_{i}",
                title=f"週次ミーティング #{i+1}",
                date=meeting_date,
                duration_sec=random.randint(1800, 5400),
                participant_count=random.randint(3, 12),
                word_count=random.randint(2000, 8000),
                action_item_count=random.randint(2, 8),
                sentiment_summary={
                    "positive": random.uniform(0.4, 0.7),
                    "neutral": random.uniform(0.2, 0.4),
                    "negative": random.uniform(0.05, 0.2),
                },
            ))

        return meetings

    async def get_productivity_report(
        self,
        tenant_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
        user_id: Optional[str] = None,
    ) -> ProductivityReport:
        """生産性レポートを取得"""
        start, end = self._get_date_range(time_range)

        return ProductivityReport(
            period_start=start,
            period_end=end,
            total_meetings=89,
            total_meeting_time_hours=48.2,
            avg_meeting_duration_min=32.5,
            action_items_created=156,
            action_items_completed=134,
            completion_rate=85.9,
            most_active_days=["月曜日", "水曜日", "金曜日"],
            peak_hours=[10, 14, 15, 16],
        )

    async def get_trend_analysis(
        self,
        tenant_id: str,
        metric: MetricType,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> TrendAnalysis:
        """トレンド分析を取得"""
        return TrendAnalysis(
            metric=metric.value,
            current_value=156,
            trend_direction="increasing",
            trend_percentage=12.5,
            forecast_next_period=175,
            seasonality_detected=True,
            anomalies=[
                {
                    "date": (datetime.utcnow() - timedelta(days=5)).isoformat(),
                    "value": 25,
                    "expected": 8,
                    "deviation": 212.5,
                }
            ],
        )


class DashboardManager:
    """ダッシュボード管理"""

    def __init__(self, analytics_engine: DashboardAnalyticsEngine):
        self.analytics = analytics_engine
        self._dashboards: Dict[str, Dict] = {}
        self._widgets: Dict[str, Dict] = {}

    async def create_dashboard(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        widgets: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """ダッシュボードを作成"""
        dashboard_id = str(uuid.uuid4())

        dashboard = {
            "id": dashboard_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "widgets": widgets or [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        self._dashboards[dashboard_id] = dashboard
        return dashboard

    async def get_dashboard(
        self,
        dashboard_id: str,
    ) -> Optional[Dict[str, Any]]:
        """ダッシュボードを取得"""
        return self._dashboards.get(dashboard_id)

    async def list_dashboards(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """ダッシュボード一覧"""
        return [
            d for d in self._dashboards.values()
            if d["tenant_id"] == tenant_id
        ]

    async def add_widget(
        self,
        dashboard_id: str,
        widget_type: str,
        title: str,
        config: Dict[str, Any],
        position: Dict[str, int] = None,
    ) -> Dict[str, Any]:
        """ウィジェットを追加"""
        widget_id = str(uuid.uuid4())

        widget = {
            "id": widget_id,
            "dashboard_id": dashboard_id,
            "type": widget_type,
            "title": title,
            "config": config,
            "position": position or {"x": 0, "y": 0, "w": 4, "h": 3},
            "created_at": datetime.utcnow(),
        }

        self._widgets[widget_id] = widget

        if dashboard_id in self._dashboards:
            self._dashboards[dashboard_id]["widgets"].append(widget)
            self._dashboards[dashboard_id]["updated_at"] = datetime.utcnow()

        return widget

    async def get_widget_data(
        self,
        widget_id: str,
        time_range: TimeRange = TimeRange.LAST_30_DAYS,
    ) -> Dict[str, Any]:
        """ウィジェットデータを取得"""
        widget = self._widgets.get(widget_id)
        if not widget:
            raise ValueError("Widget not found")

        dashboard = self._dashboards.get(widget["dashboard_id"])
        tenant_id = dashboard["tenant_id"] if dashboard else "default"

        widget_type = widget["type"]

        if widget_type == "overview_metrics":
            metrics = await self.analytics.get_overview_metrics(tenant_id, time_range)
            return {"metrics": [m.__dict__ for m in metrics]}

        elif widget_type == "transcription_trend":
            chart = await self.analytics.get_transcription_trend(tenant_id, time_range)
            return self._chart_to_dict(chart)

        elif widget_type == "duration_distribution":
            chart = await self.analytics.get_duration_distribution(tenant_id, time_range)
            return self._chart_to_dict(chart)

        elif widget_type == "speaker_analytics":
            speakers = await self.analytics.get_speaker_analytics(tenant_id)
            return {"speakers": [s.__dict__ for s in speakers]}

        elif widget_type == "productivity_report":
            report = await self.analytics.get_productivity_report(tenant_id, time_range)
            return {
                "report": {
                    **report.__dict__,
                    "period_start": report.period_start.isoformat(),
                    "period_end": report.period_end.isoformat(),
                }
            }

        return {}

    def _chart_to_dict(self, chart: ChartData) -> Dict[str, Any]:
        """チャートを辞書に変換"""
        return {
            "chart_type": chart.chart_type.value,
            "title": chart.title,
            "series": [
                {
                    "label": s.label,
                    "color": s.color,
                    "data": [
                        {"x": t.isoformat(), "y": v}
                        for t, v in zip(s.timestamps, s.values)
                    ],
                }
                for s in chart.series
            ],
            "x_axis_label": chart.x_axis_label,
            "y_axis_label": chart.y_axis_label,
            "metadata": chart.metadata,
        }


class ReportGenerator:
    """レポート生成"""

    def __init__(self, analytics_engine: DashboardAnalyticsEngine):
        self.analytics = analytics_engine

    async def generate_weekly_report(
        self,
        tenant_id: str,
        include_charts: bool = True,
    ) -> Dict[str, Any]:
        """週次レポートを生成"""
        metrics = await self.analytics.get_overview_metrics(
            tenant_id, TimeRange.LAST_7_DAYS
        )
        productivity = await self.analytics.get_productivity_report(
            tenant_id, TimeRange.LAST_7_DAYS
        )
        speakers = await self.analytics.get_speaker_analytics(
            tenant_id, time_range=TimeRange.LAST_7_DAYS
        )

        report = {
            "type": "weekly",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start": productivity.period_start.isoformat(),
                "end": productivity.period_end.isoformat(),
            },
            "summary": {
                "total_meetings": productivity.total_meetings,
                "total_meeting_hours": productivity.total_meeting_time_hours,
                "action_items_completed": productivity.action_items_completed,
                "completion_rate": productivity.completion_rate,
            },
            "metrics": [m.__dict__ for m in metrics],
            "top_speakers": [s.__dict__ for s in speakers[:5]],
            "productivity": {
                "most_active_days": productivity.most_active_days,
                "peak_hours": productivity.peak_hours,
            },
        }

        if include_charts:
            trend = await self.analytics.get_transcription_trend(
                tenant_id, TimeRange.LAST_7_DAYS
            )
            report["charts"] = {
                "transcription_trend": self._chart_to_json(trend),
            }

        return report

    async def generate_monthly_report(
        self,
        tenant_id: str,
        include_charts: bool = True,
    ) -> Dict[str, Any]:
        """月次レポートを生成"""
        metrics = await self.analytics.get_overview_metrics(
            tenant_id, TimeRange.LAST_30_DAYS
        )
        productivity = await self.analytics.get_productivity_report(
            tenant_id, TimeRange.LAST_30_DAYS
        )
        meetings = await self.analytics.get_meeting_statistics(
            tenant_id, TimeRange.LAST_30_DAYS
        )

        report = {
            "type": "monthly",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start": productivity.period_start.isoformat(),
                "end": productivity.period_end.isoformat(),
            },
            "summary": {
                "total_meetings": productivity.total_meetings,
                "total_meeting_hours": productivity.total_meeting_time_hours,
                "avg_meeting_duration": productivity.avg_meeting_duration_min,
                "action_items_created": productivity.action_items_created,
                "action_items_completed": productivity.action_items_completed,
                "completion_rate": productivity.completion_rate,
            },
            "metrics": [m.__dict__ for m in metrics],
            "meetings": [
                {
                    **m.__dict__,
                    "date": m.date.isoformat(),
                }
                for m in meetings
            ],
            "insights": self._generate_insights(metrics, productivity),
        }

        return report

    def _chart_to_json(self, chart: ChartData) -> Dict[str, Any]:
        """チャートをJSONに変換"""
        return {
            "type": chart.chart_type.value,
            "title": chart.title,
            "data": {
                "labels": [t.strftime("%Y-%m-%d") for t in chart.series[0].timestamps],
                "datasets": [
                    {
                        "label": s.label,
                        "data": s.values,
                        "color": s.color,
                    }
                    for s in chart.series
                ],
            },
        }

    def _generate_insights(
        self,
        metrics: List[DashboardMetric],
        productivity: ProductivityReport,
    ) -> List[str]:
        """インサイトを生成"""
        insights = []

        for metric in metrics:
            if metric.change_direction == "up" and (metric.change_percent or 0) > 10:
                insights.append(f"{metric.name}が前期比{metric.change_percent:.1f}%増加しました")
            elif metric.change_direction == "down" and (metric.change_percent or 0) > 10:
                insights.append(f"{metric.name}が前期比{abs(metric.change_percent or 0):.1f}%減少しました")

        if productivity.completion_rate >= 80:
            insights.append(f"アクションアイテムの完了率が{productivity.completion_rate:.1f}%と高水準を維持しています")
        elif productivity.completion_rate < 50:
            insights.append(f"アクションアイテムの完了率が{productivity.completion_rate:.1f}%と低下しています。改善が必要です")

        return insights


# グローバルインスタンス
dashboard_analytics_engine = DashboardAnalyticsEngine()
dashboard_manager = DashboardManager(dashboard_analytics_engine)
report_generator = ReportGenerator(dashboard_analytics_engine)
