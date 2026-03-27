import uuid
import re
from datetime import datetime, date, timedelta
from typing import Optional
from collections import Counter
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analytics import UsageMetrics, TranscriptionAnalytics, Report
from app.models.transcription import Transcription, TranscriptionSegment


class AnalyticsService:
    """分析サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # 使用量メトリクス
    # =========================================================================

    async def get_or_create_daily_metrics(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> UsageMetrics:
        """日次メトリクスを取得または作成"""
        query = select(UsageMetrics).where(
            UsageMetrics.user_id == user_id,
            UsageMetrics.date == target_date,
        )
        result = await self.db.execute(query)
        metrics = result.scalar_one_or_none()

        if not metrics:
            metrics = UsageMetrics(
                user_id=user_id,
                date=target_date,
            )
            self.db.add(metrics)
            await self.db.commit()

        return metrics

    async def increment_metrics(
        self,
        user_id: uuid.UUID,
        transcriptions: int = 0,
        audio_duration_sec: int = 0,
        characters: int = 0,
        words: int = 0,
        api_calls: int = 0,
        ai_tokens: int = 0,
        storage_bytes: int = 0,
    ) -> UsageMetrics:
        """メトリクスを増加"""
        metrics = await self.get_or_create_daily_metrics(user_id, date.today())

        metrics.transcriptions_count += transcriptions
        metrics.total_audio_duration_sec += audio_duration_sec
        metrics.total_characters += characters
        metrics.total_words += words
        metrics.api_calls_count += api_calls
        metrics.ai_tokens_used += ai_tokens
        metrics.storage_used_bytes += storage_bytes

        await self.db.commit()
        return metrics

    async def get_usage_summary(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """使用量サマリーを取得"""
        query = select(
            func.sum(UsageMetrics.transcriptions_count).label('total_transcriptions'),
            func.sum(UsageMetrics.total_audio_duration_sec).label('total_duration'),
            func.sum(UsageMetrics.total_characters).label('total_characters'),
            func.sum(UsageMetrics.total_words).label('total_words'),
            func.sum(UsageMetrics.api_calls_count).label('total_api_calls'),
            func.sum(UsageMetrics.ai_tokens_used).label('total_tokens'),
            func.sum(UsageMetrics.storage_used_bytes).label('total_storage'),
        ).where(
            UsageMetrics.user_id == user_id,
            UsageMetrics.date >= start_date,
            UsageMetrics.date <= end_date,
        )

        result = await self.db.execute(query)
        row = result.one()

        return {
            'total_transcriptions': row.total_transcriptions or 0,
            'total_duration_sec': row.total_duration or 0,
            'total_characters': row.total_characters or 0,
            'total_words': row.total_words or 0,
            'total_api_calls': row.total_api_calls or 0,
            'total_tokens': row.total_tokens or 0,
            'total_storage_bytes': row.total_storage or 0,
        }

    async def get_usage_trend(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        group_by: str = 'day',  # day, week, month
    ) -> list[dict]:
        """使用量トレンドを取得"""
        query = select(UsageMetrics).where(
            UsageMetrics.user_id == user_id,
            UsageMetrics.date >= start_date,
            UsageMetrics.date <= end_date,
        ).order_by(UsageMetrics.date)

        result = await self.db.execute(query)
        metrics = list(result.scalars().all())

        # グループ化
        grouped = {}
        for m in metrics:
            if group_by == 'day':
                key = m.date.isoformat()
            elif group_by == 'week':
                key = (m.date - timedelta(days=m.date.weekday())).isoformat()
            else:  # month
                key = m.date.strftime('%Y-%m')

            if key not in grouped:
                grouped[key] = {
                    'date': key,
                    'transcriptions': 0,
                    'duration_sec': 0,
                    'words': 0,
                }

            grouped[key]['transcriptions'] += m.transcriptions_count
            grouped[key]['duration_sec'] += m.total_audio_duration_sec
            grouped[key]['words'] += m.total_words

        return list(grouped.values())

    # =========================================================================
    # 文字起こし分析
    # =========================================================================

    async def analyze_transcription(
        self,
        transcription_id: uuid.UUID,
    ) -> TranscriptionAnalytics:
        """文字起こしを分析"""
        # 既存の分析を確認
        query = select(TranscriptionAnalytics).where(
            TranscriptionAnalytics.transcription_id == transcription_id
        )
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        # 文字起こしデータを取得
        trans_query = (
            select(Transcription)
            .where(Transcription.id == transcription_id)
            .options(
                selectinload(Transcription.segments),
                selectinload(Transcription.speakers),
            )
        )
        trans_result = await self.db.execute(trans_query)
        transcription = trans_result.scalar_one_or_none()

        if not transcription:
            raise ValueError("Transcription not found")

        # 分析を実行
        analytics_data = self._compute_analytics(transcription)

        if existing:
            # 更新
            for key, value in analytics_data.items():
                setattr(existing, key, value)
            await self.db.commit()
            return existing
        else:
            # 新規作成
            analytics = TranscriptionAnalytics(
                transcription_id=transcription_id,
                **analytics_data,
            )
            self.db.add(analytics)
            await self.db.commit()
            return analytics

    def _compute_analytics(self, transcription: Transcription) -> dict:
        """分析を計算"""
        segments = transcription.segments or []
        speakers = transcription.speakers or []

        # 全テキストを結合
        full_text = ' '.join(s.text for s in segments if s.text)

        # 単語を抽出（日本語対応）
        words = self._tokenize(full_text)
        word_counts = Counter(words)

        # 基本統計
        total_duration = transcription.audio_duration_sec or 0
        total_segments = len(segments)
        total_words = len(words)
        total_characters = len(full_text.replace(' ', ''))
        unique_words = len(word_counts)

        # 話者統計
        speaker_stats = {}
        speaker_map = {str(s.id): s.label for s in speakers}

        for speaker in speakers:
            speaker_segments = [s for s in segments if str(s.speaker_id) == str(speaker.id)]
            speaker_text = ' '.join(s.text for s in speaker_segments if s.text)
            speaker_words = self._tokenize(speaker_text)
            speaker_duration = sum(
                (s.end_time_ms - s.start_time_ms) / 1000
                for s in speaker_segments
            )

            speaker_stats[str(speaker.id)] = {
                'label': speaker.label,
                'segment_count': len(speaker_segments),
                'word_count': len(speaker_words),
                'duration_sec': speaker_duration,
                'speaking_rate_wpm': (len(speaker_words) / speaker_duration * 60) if speaker_duration > 0 else 0,
            }

        # 発話速度
        speaking_rate = (total_words / total_duration * 60) if total_duration > 0 else 0

        # フィラーワード検出
        filler_patterns = ['えーと', 'あのー', 'まあ', 'その', 'なんか', 'えー', 'あー', 'うーん']
        filler_count = sum(full_text.count(f) for f in filler_patterns)

        # キーワード抽出（頻出語）
        keywords = [
            {'word': word, 'count': count}
            for word, count in word_counts.most_common(20)
            if len(word) > 1  # 1文字は除外
        ]

        # 信頼度
        confidences = [s.confidence for s in segments if s.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return {
            'total_duration_sec': total_duration,
            'total_segments': total_segments,
            'total_words': total_words,
            'total_characters': total_characters,
            'unique_words': unique_words,
            'speaker_count': len(speakers),
            'speaker_stats': speaker_stats,
            'speaking_rate_wpm': speaking_rate,
            'filler_word_count': filler_count,
            'keywords': keywords,
            'overall_confidence': avg_confidence,
        }

    def _tokenize(self, text: str) -> list[str]:
        """テキストを単語に分割（簡易版）"""
        # 日本語と英語の両方に対応
        # 実際のプロダクションではMeCabやSudachiを使用
        words = re.findall(r'[一-龥ぁ-んァ-ン]+|[a-zA-Z]+', text)
        return [w.lower() for w in words if len(w) > 0]

    async def get_transcription_analytics(
        self,
        transcription_id: uuid.UUID,
    ) -> Optional[TranscriptionAnalytics]:
        """文字起こし分析を取得"""
        query = select(TranscriptionAnalytics).where(
            TranscriptionAnalytics.transcription_id == transcription_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # =========================================================================
    # レポート
    # =========================================================================

    async def create_report(
        self,
        user_id: uuid.UUID,
        name: str,
        report_type: str,
        config: dict,
        description: Optional[str] = None,
        team_id: Optional[uuid.UUID] = None,
        schedule: Optional[dict] = None,
    ) -> Report:
        """レポートを作成"""
        report = Report(
            user_id=user_id,
            team_id=team_id,
            name=name,
            description=description,
            report_type=report_type,
            config=config,
            schedule=schedule,
        )
        self.db.add(report)
        await self.db.commit()
        return report

    async def list_reports(
        self,
        user_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
    ) -> list[Report]:
        """レポート一覧を取得"""
        conditions = [Report.user_id == user_id]
        if team_id:
            conditions.append(Report.team_id == team_id)

        query = select(Report).where(and_(*conditions)).order_by(desc(Report.updated_at))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def run_report(
        self,
        report_id: uuid.UUID,
    ) -> dict:
        """レポートを実行"""
        query = select(Report).where(Report.id == report_id)
        result = await self.db.execute(query)
        report = result.scalar_one_or_none()

        if not report:
            raise ValueError("Report not found")

        config = report.config
        report_result = {}

        if report.report_type == 'usage':
            # 使用量レポート
            start_date = datetime.fromisoformat(config.get('start_date', (datetime.now() - timedelta(days=30)).isoformat())).date()
            end_date = datetime.fromisoformat(config.get('end_date', datetime.now().isoformat())).date()

            report_result = {
                'summary': await self.get_usage_summary(report.user_id, start_date, end_date),
                'trend': await self.get_usage_trend(
                    report.user_id, start_date, end_date,
                    config.get('group_by', 'day')
                ),
            }

        elif report.report_type == 'transcription':
            # 文字起こし分析レポート
            transcription_ids = config.get('transcription_ids', [])
            analyses = []

            for tid in transcription_ids:
                analytics = await self.get_transcription_analytics(uuid.UUID(tid))
                if analytics:
                    analyses.append({
                        'transcription_id': str(analytics.transcription_id),
                        'total_duration_sec': analytics.total_duration_sec,
                        'total_words': analytics.total_words,
                        'speaker_count': analytics.speaker_count,
                        'speaking_rate_wpm': analytics.speaking_rate_wpm,
                        'keywords': analytics.keywords,
                    })

            report_result = {'analyses': analyses}

        # 結果を保存
        report.last_run_at = datetime.utcnow()
        report.last_result = report_result
        await self.db.commit()

        return report_result

    async def delete_report(self, report_id: uuid.UUID) -> bool:
        """レポートを削除"""
        query = select(Report).where(Report.id == report_id)
        result = await self.db.execute(query)
        report = result.scalar_one_or_none()

        if not report:
            return False

        await self.db.delete(report)
        await self.db.commit()
        return True


class DashboardService:
    """ダッシュボードサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_stats(
        self,
        user_id: uuid.UUID,
    ) -> dict:
        """ダッシュボード統計を取得"""
        # 今月の使用量
        today = date.today()
        month_start = today.replace(day=1)

        analytics_service = AnalyticsService(self.db)
        monthly_usage = await analytics_service.get_usage_summary(user_id, month_start, today)

        # 直近7日間のトレンド
        week_start = today - timedelta(days=6)
        weekly_trend = await analytics_service.get_usage_trend(user_id, week_start, today, 'day')

        # 最近の文字起こし
        recent_query = (
            select(Transcription)
            .where(Transcription.user_id == user_id)
            .order_by(desc(Transcription.created_at))
            .limit(5)
        )
        recent_result = await self.db.execute(recent_query)
        recent_transcriptions = list(recent_result.scalars().all())

        # 話者統計（今月）
        speaker_query = (
            select(Transcription)
            .where(
                Transcription.user_id == user_id,
                Transcription.created_at >= month_start,
            )
            .options(selectinload(Transcription.speakers))
        )
        speaker_result = await self.db.execute(speaker_query)
        transcriptions = list(speaker_result.scalars().all())

        speaker_counts = Counter()
        for t in transcriptions:
            for s in t.speakers:
                speaker_counts[s.label] += 1

        return {
            'monthly_usage': monthly_usage,
            'weekly_trend': weekly_trend,
            'recent_transcriptions': [
                {
                    'id': str(t.id),
                    'title': t.title,
                    'status': t.status,
                    'duration_sec': t.audio_duration_sec,
                    'created_at': t.created_at.isoformat(),
                }
                for t in recent_transcriptions
            ],
            'top_speakers': [
                {'label': label, 'count': count}
                for label, count in speaker_counts.most_common(5)
            ],
        }
