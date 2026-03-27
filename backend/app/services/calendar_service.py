"""カレンダー・スケジュール連携サービス"""

import os
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio


class CalendarProvider(str, Enum):
    GOOGLE = "google"
    OUTLOOK = "outlook"
    APPLE = "apple"


class EventType(str, Enum):
    MEETING = "meeting"
    CALL = "call"
    WEBINAR = "webinar"
    INTERVIEW = "interview"
    OTHER = "other"


class RecordingMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    DISABLED = "disabled"


@dataclass
class CalendarCredentials:
    """カレンダー認証情報"""
    provider: CalendarProvider
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    calendar_id: Optional[str] = None


@dataclass
class CalendarEvent:
    """カレンダーイベント"""
    id: str
    provider: CalendarProvider
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    meeting_url: Optional[str] = None
    organizer: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    event_type: EventType = EventType.MEETING
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    reminder_minutes: List[int] = field(default_factory=list)
    transcription_enabled: bool = False
    transcription_id: Optional[str] = None


@dataclass
class RecordingSchedule:
    """録音スケジュール"""
    id: str
    event_id: str
    calendar_provider: CalendarProvider
    scheduled_start: datetime
    scheduled_end: datetime
    recording_mode: RecordingMode
    auto_transcribe: bool
    notify_participants: bool
    share_transcription: bool
    status: str  # pending, in_progress, completed, cancelled


@dataclass
class MeetingReminder:
    """会議リマインダー"""
    id: str
    event_id: str
    reminder_time: datetime
    message: str
    sent: bool = False
    channels: List[str] = field(default_factory=list)  # email, slack, push


# =====================
# Google Calendar連携
# =====================

class GoogleCalendarIntegration:
    """Google Calendar連携"""

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self._credentials: Dict[str, CalendarCredentials] = {}
        self._events: Dict[str, List[CalendarEvent]] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ]
        scope_str = "%20".join(scopes)

        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_str}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> CalendarCredentials:
        """認証コードをトークンに交換"""
        return CalendarCredentials(
            provider=CalendarProvider.GOOGLE,
            access_token=f"google_cal_{uuid.uuid4().hex[:20]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            calendar_id="primary",
        )

    def store_credentials(self, tenant_id: str, credentials: CalendarCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[CalendarCredentials]:
        return self._credentials.get(tenant_id)

    async def list_calendars(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """カレンダー一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google Calendar")

        return [
            {"id": "primary", "name": "メインカレンダー", "primary": True},
            {"id": "work", "name": "仕事", "primary": False},
            {"id": "meetings", "name": "ミーティング", "primary": False},
        ]

    async def list_events(
        self,
        tenant_id: str,
        calendar_id: str = "primary",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_results: int = 50,
    ) -> List[CalendarEvent]:
        """イベント一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google Calendar")

        start = start_time or datetime.utcnow()
        end = end_time or start + timedelta(days=7)

        # シミュレーションデータ
        events = []
        import random
        random.seed(42)

        meeting_titles = [
            "週次チームミーティング",
            "プロジェクト進捗確認",
            "クライアント打ち合わせ",
            "1on1ミーティング",
            "全体会議",
        ]

        for i in range(min(max_results, 10)):
            event_start = start + timedelta(days=i, hours=random.randint(9, 16))
            event_end = event_start + timedelta(minutes=random.choice([30, 45, 60]))

            events.append(CalendarEvent(
                id=f"event_{uuid.uuid4().hex[:8]}",
                provider=CalendarProvider.GOOGLE,
                title=random.choice(meeting_titles),
                description="会議の説明",
                start_time=event_start,
                end_time=event_end,
                location="オンライン",
                meeting_url=f"https://meet.google.com/{uuid.uuid4().hex[:10]}",
                organizer="organizer@example.com",
                attendees=["participant1@example.com", "participant2@example.com"],
                event_type=EventType.MEETING,
            ))

        return events

    async def get_event(
        self,
        tenant_id: str,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Optional[CalendarEvent]:
        """イベントを取得"""
        events = await self.list_events(tenant_id, calendar_id)
        return next((e for e in events if e.id == event_id), None)

    async def watch_events(
        self,
        tenant_id: str,
        calendar_id: str = "primary",
        webhook_url: str = "",
    ) -> Dict[str, Any]:
        """イベント変更を監視"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google Calendar")

        return {
            "channel_id": str(uuid.uuid4()),
            "resource_id": calendar_id,
            "webhook_url": webhook_url,
            "expiration": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        }


# =====================
# Outlook Calendar連携
# =====================

class OutlookCalendarIntegration:
    """Outlook Calendar連携"""

    def __init__(self):
        self.client_id = os.getenv("OUTLOOK_CLIENT_ID", "")
        self.client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "")
        self._credentials: Dict[str, CalendarCredentials] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = [
            "Calendars.Read",
            "Calendars.ReadWrite",
            "OnlineMeetings.Read",
        ]
        scope_str = "%20".join(scopes)

        auth_url = (
            f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"
            f"client_id={self.client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope_str}"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> CalendarCredentials:
        """認証コードをトークンに交換"""
        return CalendarCredentials(
            provider=CalendarProvider.OUTLOOK,
            access_token=f"outlook_cal_{uuid.uuid4().hex[:20]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

    def store_credentials(self, tenant_id: str, credentials: CalendarCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[CalendarCredentials]:
        return self._credentials.get(tenant_id)

    async def list_calendars(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """カレンダー一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Outlook Calendar")

        return [
            {"id": "default", "name": "予定表", "primary": True},
            {"id": "work", "name": "仕事", "primary": False},
        ]

    async def list_events(
        self,
        tenant_id: str,
        calendar_id: str = "default",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_results: int = 50,
    ) -> List[CalendarEvent]:
        """イベント一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Outlook Calendar")

        start = start_time or datetime.utcnow()
        end = end_time or start + timedelta(days=7)

        # シミュレーションデータ
        events = []
        import random
        random.seed(43)

        for i in range(min(max_results, 8)):
            event_start = start + timedelta(days=i, hours=random.randint(9, 16))
            event_end = event_start + timedelta(minutes=random.choice([30, 60]))

            events.append(CalendarEvent(
                id=f"outlook_event_{uuid.uuid4().hex[:8]}",
                provider=CalendarProvider.OUTLOOK,
                title=f"Teams会議 #{i+1}",
                description="",
                start_time=event_start,
                end_time=event_end,
                meeting_url=f"https://teams.microsoft.com/l/meetup-join/{uuid.uuid4().hex}",
                event_type=EventType.MEETING,
            ))

        return events


# =====================
# 録音スケジューラー
# =====================

class RecordingScheduler:
    """録音スケジューラー"""

    def __init__(
        self,
        google_calendar: GoogleCalendarIntegration,
        outlook_calendar: OutlookCalendarIntegration,
    ):
        self.google = google_calendar
        self.outlook = outlook_calendar
        self._schedules: Dict[str, RecordingSchedule] = {}
        self._auto_record_settings: Dict[str, Dict[str, Any]] = {}

    async def setup_auto_recording(
        self,
        tenant_id: str,
        provider: CalendarProvider,
        calendar_id: str,
        mode: RecordingMode = RecordingMode.AUTO,
        auto_transcribe: bool = True,
        event_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """自動録音を設定"""
        config_id = f"{tenant_id}_{provider.value}_{calendar_id}"

        self._auto_record_settings[config_id] = {
            "tenant_id": tenant_id,
            "provider": provider,
            "calendar_id": calendar_id,
            "mode": mode,
            "auto_transcribe": auto_transcribe,
            "event_filters": event_filters or {},
            "enabled": True,
            "created_at": datetime.utcnow(),
        }

        return self._auto_record_settings[config_id]

    async def schedule_recording(
        self,
        tenant_id: str,
        event_id: str,
        provider: CalendarProvider,
        mode: RecordingMode = RecordingMode.AUTO,
        auto_transcribe: bool = True,
        notify_participants: bool = False,
        share_transcription: bool = False,
    ) -> RecordingSchedule:
        """録音をスケジュール"""
        # イベントを取得
        if provider == CalendarProvider.GOOGLE:
            event = await self.google.get_event(tenant_id, event_id)
        elif provider == CalendarProvider.OUTLOOK:
            events = await self.outlook.list_events(tenant_id)
            event = next((e for e in events if e.id == event_id), None)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        if not event:
            raise ValueError("Event not found")

        schedule_id = str(uuid.uuid4())

        schedule = RecordingSchedule(
            id=schedule_id,
            event_id=event_id,
            calendar_provider=provider,
            scheduled_start=event.start_time,
            scheduled_end=event.end_time,
            recording_mode=mode,
            auto_transcribe=auto_transcribe,
            notify_participants=notify_participants,
            share_transcription=share_transcription,
            status="pending",
        )

        self._schedules[schedule_id] = schedule
        return schedule

    async def get_upcoming_schedules(
        self,
        tenant_id: str,
        hours_ahead: int = 24,
    ) -> List[RecordingSchedule]:
        """今後のスケジュールを取得"""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours_ahead)

        schedules = [
            s for s in self._schedules.values()
            if s.scheduled_start >= now and s.scheduled_start <= cutoff
            and s.status == "pending"
        ]

        schedules.sort(key=lambda x: x.scheduled_start)
        return schedules

    async def cancel_schedule(
        self,
        schedule_id: str,
    ) -> bool:
        """スケジュールをキャンセル"""
        if schedule_id in self._schedules:
            self._schedules[schedule_id].status = "cancelled"
            return True
        return False

    async def sync_calendar_events(
        self,
        tenant_id: str,
        provider: CalendarProvider,
    ) -> List[RecordingSchedule]:
        """カレンダーイベントを同期してスケジュールを作成"""
        config_key = None
        for key, config in self._auto_record_settings.items():
            if config["tenant_id"] == tenant_id and config["provider"] == provider:
                if config["enabled"]:
                    config_key = key
                    break

        if not config_key:
            return []

        config = self._auto_record_settings[config_key]

        # イベントを取得
        if provider == CalendarProvider.GOOGLE:
            events = await self.google.list_events(
                tenant_id,
                config["calendar_id"],
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(days=7),
            )
        else:
            events = await self.outlook.list_events(
                tenant_id,
                config["calendar_id"],
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(days=7),
            )

        # 新規イベントをスケジュール
        new_schedules = []
        existing_event_ids = {s.event_id for s in self._schedules.values()}

        for event in events:
            if event.id not in existing_event_ids:
                # フィルターをチェック
                if self._matches_filter(event, config.get("event_filters", {})):
                    schedule = await self.schedule_recording(
                        tenant_id=tenant_id,
                        event_id=event.id,
                        provider=provider,
                        mode=config["mode"],
                        auto_transcribe=config["auto_transcribe"],
                    )
                    new_schedules.append(schedule)

        return new_schedules

    def _matches_filter(
        self,
        event: CalendarEvent,
        filters: Dict[str, Any],
    ) -> bool:
        """イベントがフィルターにマッチするか"""
        if not filters:
            return True

        # タイトルフィルター
        if "title_contains" in filters:
            if filters["title_contains"].lower() not in event.title.lower():
                return False

        # 最小時間フィルター
        if "min_duration_minutes" in filters:
            duration = (event.end_time - event.start_time).total_seconds() / 60
            if duration < filters["min_duration_minutes"]:
                return False

        # 参加者数フィルター
        if "min_attendees" in filters:
            if len(event.attendees) < filters["min_attendees"]:
                return False

        return True


# =====================
# 会議後フォローアップ
# =====================

class MeetingFollowupManager:
    """会議後フォローアップ管理"""

    def __init__(self):
        self._followups: Dict[str, Dict[str, Any]] = {}
        self._reminders: Dict[str, MeetingReminder] = {}

    async def create_followup(
        self,
        tenant_id: str,
        transcription_id: str,
        event_id: str,
        attendees: List[str],
        actions: List[str],
    ) -> Dict[str, Any]:
        """フォローアップを作成"""
        followup_id = str(uuid.uuid4())

        followup = {
            "id": followup_id,
            "tenant_id": tenant_id,
            "transcription_id": transcription_id,
            "event_id": event_id,
            "attendees": attendees,
            "actions": actions,
            "status": "pending",
            "created_at": datetime.utcnow(),
        }

        self._followups[followup_id] = followup
        return followup

    async def send_transcription_summary(
        self,
        followup_id: str,
        summary: str,
        action_items: List[Dict[str, Any]],
        transcription_url: str,
    ) -> Dict[str, Any]:
        """文字起こしサマリーを送信"""
        followup = self._followups.get(followup_id)
        if not followup:
            raise ValueError("Followup not found")

        # シミュレーション
        followup["status"] = "sent"
        followup["sent_at"] = datetime.utcnow()

        return {
            "followup_id": followup_id,
            "recipients": followup["attendees"],
            "status": "sent",
            "sent_at": followup["sent_at"].isoformat(),
        }

    async def create_reminder(
        self,
        tenant_id: str,
        event_id: str,
        reminder_time: datetime,
        message: str,
        channels: List[str],
    ) -> MeetingReminder:
        """リマインダーを作成"""
        reminder_id = str(uuid.uuid4())

        reminder = MeetingReminder(
            id=reminder_id,
            event_id=event_id,
            reminder_time=reminder_time,
            message=message,
            channels=channels,
        )

        self._reminders[reminder_id] = reminder
        return reminder

    async def get_pending_reminders(
        self,
        tenant_id: str,
    ) -> List[MeetingReminder]:
        """未送信のリマインダーを取得"""
        now = datetime.utcnow()
        return [
            r for r in self._reminders.values()
            if not r.sent and r.reminder_time <= now
        ]

    async def mark_reminder_sent(
        self,
        reminder_id: str,
    ) -> bool:
        """リマインダーを送信済みにマーク"""
        if reminder_id in self._reminders:
            self._reminders[reminder_id].sent = True
            return True
        return False


# グローバルインスタンス
google_calendar = GoogleCalendarIntegration()
outlook_calendar = OutlookCalendarIntegration()
recording_scheduler = RecordingScheduler(google_calendar, outlook_calendar)
meeting_followup_manager = MeetingFollowupManager()
