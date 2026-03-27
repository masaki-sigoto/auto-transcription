"""ビデオ会議連携サービス"""

from typing import Optional, AsyncGenerator
from datetime import datetime, timedelta
from uuid import UUID
import asyncio
import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()


class MeetingInfo(BaseModel):
    """会議情報"""
    id: str
    title: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_minutes: Optional[int]
    participants: list[str]
    recording_url: Optional[str]
    provider: str  # zoom, teams, meet


class ZoomService:
    """Zoom連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url="https://api.zoom.us/v2",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def get_meetings(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[MeetingInfo]:
        """会議一覧を取得"""
        params = {"type": "scheduled", "page_size": 50}

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")

        response = await self.client.get("/users/me/meetings", params=params)
        response.raise_for_status()
        data = response.json()

        meetings = []
        for m in data.get("meetings", []):
            meetings.append(
                MeetingInfo(
                    id=str(m["id"]),
                    title=m["topic"],
                    start_time=datetime.fromisoformat(m["start_time"].replace("Z", "+00:00")),
                    end_time=None,
                    duration_minutes=m.get("duration"),
                    participants=[],
                    recording_url=None,
                    provider="zoom",
                )
            )

        return meetings

    async def get_recordings(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[dict]:
        """録画一覧を取得"""
        params = {"page_size": 50}

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")

        response = await self.client.get("/users/me/recordings", params=params)
        response.raise_for_status()
        data = response.json()

        recordings = []
        for meeting in data.get("meetings", []):
            for file in meeting.get("recording_files", []):
                if file.get("file_type") == "MP4":
                    recordings.append({
                        "meeting_id": str(meeting["id"]),
                        "meeting_title": meeting["topic"],
                        "recording_id": file["id"],
                        "download_url": file["download_url"],
                        "file_size": file.get("file_size"),
                        "duration": file.get("recording_end") and file.get("recording_start"),
                        "start_time": meeting.get("start_time"),
                    })

        return recordings

    async def download_recording(self, download_url: str) -> AsyncGenerator[bytes, None]:
        """録画をダウンロード"""
        async with self.client.stream(
            "GET",
            download_url,
            params={"access_token": self.access_token},
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                yield chunk

    async def create_meeting(
        self,
        topic: str,
        start_time: datetime,
        duration_minutes: int = 60,
        settings: Optional[dict] = None,
    ) -> MeetingInfo:
        """会議を作成"""
        payload = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": duration_minutes,
            "settings": settings or {
                "auto_recording": "cloud",
                "join_before_host": True,
            },
        }

        response = await self.client.post("/users/me/meetings", json=payload)
        response.raise_for_status()
        data = response.json()

        return MeetingInfo(
            id=str(data["id"]),
            title=data["topic"],
            start_time=datetime.fromisoformat(data["start_time"].replace("Z", "+00:00")),
            end_time=None,
            duration_minutes=data.get("duration"),
            participants=[],
            recording_url=None,
            provider="zoom",
        )

    async def close(self):
        await self.client.aclose()


class TeamsService:
    """Microsoft Teams連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def get_meetings(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[MeetingInfo]:
        """会議一覧を取得"""
        # カレンダーイベントからTeams会議を取得
        start = (from_date or datetime.utcnow()).isoformat() + "Z"
        end = (to_date or datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"

        response = await self.client.get(
            "/me/calendar/calendarView",
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$filter": "isOnlineMeeting eq true",
            },
        )
        response.raise_for_status()
        data = response.json()

        meetings = []
        for event in data.get("value", []):
            online_meeting = event.get("onlineMeeting", {})
            meetings.append(
                MeetingInfo(
                    id=event["id"],
                    title=event["subject"],
                    start_time=datetime.fromisoformat(event["start"]["dateTime"]),
                    end_time=datetime.fromisoformat(event["end"]["dateTime"]),
                    duration_minutes=None,
                    participants=[
                        a["emailAddress"]["address"]
                        for a in event.get("attendees", [])
                    ],
                    recording_url=online_meeting.get("joinUrl"),
                    provider="teams",
                )
            )

        return meetings

    async def get_call_records(self) -> list[dict]:
        """通話記録を取得"""
        response = await self.client.get("/communications/callRecords")
        response.raise_for_status()
        return response.json().get("value", [])

    async def close(self):
        await self.client.aclose()


class GoogleMeetService:
    """Google Meet連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def get_meetings(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[MeetingInfo]:
        """カレンダーからMeet会議を取得"""
        calendar_api = "https://www.googleapis.com/calendar/v3"

        time_min = (from_date or datetime.utcnow()).isoformat() + "Z"
        time_max = (to_date or datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"

        response = await self.client.get(
            f"{calendar_api}/calendars/primary/events",
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        response.raise_for_status()
        data = response.json()

        meetings = []
        for event in data.get("items", []):
            # Google Meet URLが含まれているイベントのみ
            conference_data = event.get("conferenceData", {})
            entry_points = conference_data.get("entryPoints", [])
            meet_url = next(
                (ep["uri"] for ep in entry_points if ep.get("entryPointType") == "video"),
                None,
            )

            if meet_url:
                meetings.append(
                    MeetingInfo(
                        id=event["id"],
                        title=event.get("summary", "Untitled Meeting"),
                        start_time=datetime.fromisoformat(
                            event["start"].get("dateTime", event["start"].get("date"))
                        ),
                        end_time=datetime.fromisoformat(
                            event["end"].get("dateTime", event["end"].get("date"))
                        ) if event.get("end") else None,
                        duration_minutes=None,
                        participants=[
                            a["email"] for a in event.get("attendees", [])
                        ],
                        recording_url=meet_url,
                        provider="meet",
                    )
                )

        return meetings

    async def close(self):
        await self.client.aclose()


class VideoMeetingIntegrationService:
    """ビデオ会議統合サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_recording(
        self,
        provider: str,
        meeting_id: str,
        access_token: str,
    ) -> dict:
        """録画をインポートして文字起こし"""
        # プロバイダーに応じたサービスを取得
        if provider == "zoom":
            service = ZoomService(access_token)
            # 録画をダウンロードしてアップロード
            # ...
        elif provider == "teams":
            service = TeamsService(access_token)
        elif provider == "meet":
            service = GoogleMeetService(access_token)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # 実装: 録画をダウンロード → S3にアップロード → 文字起こしジョブ作成

        return {
            "status": "processing",
            "meeting_id": meeting_id,
            "provider": provider,
        }
