"""カレンダー・スケジュール連携APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.calendar_service import (
    google_calendar,
    outlook_calendar,
    recording_scheduler,
    meeting_followup_manager,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


async def get_current_user_id() -> str:
    return "default-user"


async def get_current_tenant_id() -> str:
    return "default-tenant"


# =====================
# Google Calendar
# =====================

@router.get("/google/auth")
async def google_auth_url(
    user_id: str = Depends(get_current_user_id),
):
    """Google Calendar OAuth URLを取得"""
    url = await google_calendar.get_auth_url(user_id)
    return {"auth_url": url, "provider": "google"}


@router.post("/google/callback")
async def google_callback(
    code: str,
    user_id: str = Depends(get_current_user_id),
):
    """Google Calendar OAuthコールバック"""
    success = await google_calendar.handle_callback(user_id, code)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to authenticate with Google")

    return {"status": "connected", "provider": "google"}


@router.get("/google/events")
async def list_google_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = Query(default=50, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Googleカレンダーのイベント一覧"""
    events = await google_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
    )

    return {
        "events": [
            {
                "id": e.event_id,
                "title": e.title,
                "start": e.start_time.isoformat(),
                "end": e.end_time.isoformat(),
                "attendees": e.attendees,
                "meeting_url": e.meeting_url,
                "is_online_meeting": e.is_online_meeting,
            }
            for e in events
        ],
        "count": len(events),
        "provider": "google",
    }


@router.get("/google/meetings")
async def list_google_meetings(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Googleカレンダーのオンライン会議一覧"""
    events = await google_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    # オンライン会議のみフィルタ
    meetings = [e for e in events if e.is_online_meeting]

    return {
        "meetings": [
            {
                "id": e.event_id,
                "title": e.title,
                "start": e.start_time.isoformat(),
                "end": e.end_time.isoformat(),
                "attendees": e.attendees,
                "meeting_url": e.meeting_url,
                "provider": e.metadata.get("provider", "unknown"),
            }
            for e in meetings
        ],
        "count": len(meetings),
    }


# =====================
# Outlook Calendar
# =====================

@router.get("/outlook/auth")
async def outlook_auth_url(
    user_id: str = Depends(get_current_user_id),
):
    """Outlook Calendar OAuth URLを取得"""
    url = await outlook_calendar.get_auth_url(user_id)
    return {"auth_url": url, "provider": "outlook"}


@router.post("/outlook/callback")
async def outlook_callback(
    code: str,
    user_id: str = Depends(get_current_user_id),
):
    """Outlook Calendar OAuthコールバック"""
    success = await outlook_calendar.handle_callback(user_id, code)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to authenticate with Outlook")

    return {"status": "connected", "provider": "outlook"}


@router.get("/outlook/events")
async def list_outlook_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = Query(default=50, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Outlookカレンダーのイベント一覧"""
    events = await outlook_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
    )

    return {
        "events": [
            {
                "id": e.event_id,
                "title": e.title,
                "start": e.start_time.isoformat(),
                "end": e.end_time.isoformat(),
                "attendees": e.attendees,
                "meeting_url": e.meeting_url,
                "is_online_meeting": e.is_online_meeting,
            }
            for e in events
        ],
        "count": len(events),
        "provider": "outlook",
    }


@router.get("/outlook/meetings")
async def list_outlook_meetings(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Outlookカレンダーのオンライン会議一覧"""
    events = await outlook_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    meetings = [e for e in events if e.is_online_meeting]

    return {
        "meetings": [
            {
                "id": e.event_id,
                "title": e.title,
                "start": e.start_time.isoformat(),
                "end": e.end_time.isoformat(),
                "attendees": e.attendees,
                "meeting_url": e.meeting_url,
                "provider": e.metadata.get("provider", "teams"),
            }
            for e in meetings
        ],
        "count": len(meetings),
    }


# =====================
# 統合カレンダー
# =====================

@router.get("/events")
async def list_all_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """全カレンダーのイベント統合一覧"""
    google_events = await google_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    outlook_events = await outlook_calendar.get_events(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    all_events = []

    for e in google_events:
        all_events.append({
            "id": e.event_id,
            "title": e.title,
            "start": e.start_time.isoformat(),
            "end": e.end_time.isoformat(),
            "attendees": e.attendees,
            "meeting_url": e.meeting_url,
            "is_online_meeting": e.is_online_meeting,
            "source": "google",
        })

    for e in outlook_events:
        all_events.append({
            "id": e.event_id,
            "title": e.title,
            "start": e.start_time.isoformat(),
            "end": e.end_time.isoformat(),
            "attendees": e.attendees,
            "meeting_url": e.meeting_url,
            "is_online_meeting": e.is_online_meeting,
            "source": "outlook",
        })

    # 開始時間でソート
    all_events.sort(key=lambda x: x["start"])

    return {
        "events": all_events,
        "count": len(all_events),
    }


# =====================
# 録画スケジューラ
# =====================

class AutoRecordingRequest(BaseModel):
    calendar_source: str  # google, outlook
    filter_keywords: List[str] = []
    exclude_keywords: List[str] = []
    min_duration_minutes: int = 15
    auto_transcribe: bool = True


@router.post("/recording/auto-setup")
async def setup_auto_recording(
    request: AutoRecordingRequest,
    user_id: str = Depends(get_current_user_id),
):
    """自動録画設定"""
    config = await recording_scheduler.setup_auto_recording(
        user_id=user_id,
        calendar_source=request.calendar_source,
        filter_keywords=request.filter_keywords,
        exclude_keywords=request.exclude_keywords,
        min_duration_minutes=request.min_duration_minutes,
        auto_transcribe=request.auto_transcribe,
    )

    return {
        "id": config["id"],
        "calendar_source": config["calendar_source"],
        "filter_keywords": config["filter_keywords"],
        "auto_transcribe": config["auto_transcribe"],
        "status": "active",
    }


@router.get("/recording/auto-setup")
async def get_auto_recording_config(
    user_id: str = Depends(get_current_user_id),
):
    """自動録画設定を取得"""
    config = recording_scheduler._user_configs.get(user_id)

    if not config:
        return {"configured": False}

    return {
        "configured": True,
        "id": config["id"],
        "calendar_source": config["calendar_source"],
        "filter_keywords": config["filter_keywords"],
        "exclude_keywords": config["exclude_keywords"],
        "min_duration_minutes": config["min_duration_minutes"],
        "auto_transcribe": config["auto_transcribe"],
    }


@router.delete("/recording/auto-setup")
async def disable_auto_recording(
    user_id: str = Depends(get_current_user_id),
):
    """自動録画を無効化"""
    if user_id in recording_scheduler._user_configs:
        del recording_scheduler._user_configs[user_id]

    return {"status": "disabled"}


class ScheduleRecordingRequest(BaseModel):
    event_id: str
    calendar_source: str
    auto_transcribe: bool = True


@router.post("/recording/schedule")
async def schedule_recording(
    request: ScheduleRecordingRequest,
    user_id: str = Depends(get_current_user_id),
):
    """個別イベントの録画をスケジュール"""
    scheduled = await recording_scheduler.schedule_recording(
        user_id=user_id,
        event_id=request.event_id,
        calendar_source=request.calendar_source,
        auto_transcribe=request.auto_transcribe,
    )

    return {
        "id": scheduled["id"],
        "event_id": scheduled["event_id"],
        "event_title": scheduled["event_title"],
        "scheduled_start": scheduled["start_time"].isoformat(),
        "auto_transcribe": scheduled["auto_transcribe"],
        "status": scheduled["status"],
    }


@router.get("/recording/scheduled")
async def list_scheduled_recordings(
    user_id: str = Depends(get_current_user_id),
):
    """スケジュール済み録画一覧"""
    recordings = recording_scheduler._scheduled_recordings.get(user_id, [])

    return {
        "recordings": [
            {
                "id": r["id"],
                "event_id": r["event_id"],
                "event_title": r["event_title"],
                "scheduled_start": r["start_time"].isoformat(),
                "scheduled_end": r["end_time"].isoformat(),
                "auto_transcribe": r["auto_transcribe"],
                "status": r["status"],
            }
            for r in recordings
        ],
        "count": len(recordings),
    }


@router.delete("/recording/scheduled/{recording_id}")
async def cancel_scheduled_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """スケジュール済み録画をキャンセル"""
    recordings = recording_scheduler._scheduled_recordings.get(user_id, [])
    recording_scheduler._scheduled_recordings[user_id] = [
        r for r in recordings if r["id"] != recording_id
    ]

    return {"status": "cancelled", "recording_id": recording_id}


@router.post("/recording/sync")
async def sync_calendar_recordings(
    calendar_source: str = "google",
    user_id: str = Depends(get_current_user_id),
):
    """カレンダーと録画スケジュールを同期"""
    synced = await recording_scheduler.sync_calendar_events(
        user_id=user_id,
        calendar_source=calendar_source,
    )

    return {
        "synced_count": synced,
        "calendar_source": calendar_source,
        "status": "synced",
    }


# =====================
# ミーティングフォローアップ
# =====================

class CreateFollowupRequest(BaseModel):
    transcription_id: str
    event_id: Optional[str] = None
    send_to_attendees: bool = True
    include_summary: bool = True
    include_action_items: bool = True


@router.post("/followup")
async def create_meeting_followup(
    request: CreateFollowupRequest,
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ミーティングフォローアップを作成"""
    followup = await meeting_followup_manager.create_followup(
        tenant_id=tenant_id,
        transcription_id=request.transcription_id,
        event_id=request.event_id,
        send_to_attendees=request.send_to_attendees,
        include_summary=request.include_summary,
        include_action_items=request.include_action_items,
    )

    return {
        "id": followup["id"],
        "transcription_id": followup["transcription_id"],
        "summary": followup["summary"],
        "action_items": followup["action_items"],
        "recipients": followup["recipients"],
        "sent_at": followup["sent_at"].isoformat() if followup.get("sent_at") else None,
        "status": followup["status"],
    }


@router.get("/followup/{transcription_id}")
async def get_followup(
    transcription_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """フォローアップを取得"""
    followup = meeting_followup_manager._followups.get(transcription_id)

    if not followup:
        raise HTTPException(status_code=404, detail="Followup not found")

    return {
        "id": followup["id"],
        "transcription_id": followup["transcription_id"],
        "summary": followup["summary"],
        "action_items": followup["action_items"],
        "recipients": followup["recipients"],
        "sent_at": followup["sent_at"].isoformat() if followup.get("sent_at") else None,
        "status": followup["status"],
    }


class SendSummaryRequest(BaseModel):
    transcription_id: str
    recipients: List[str]
    subject: Optional[str] = None


@router.post("/followup/send-summary")
async def send_transcription_summary(
    request: SendSummaryRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こし要約を送信"""
    result = await meeting_followup_manager.send_transcription_summary(
        tenant_id=tenant_id,
        transcription_id=request.transcription_id,
        recipients=request.recipients,
        subject=request.subject,
    )

    return {
        "transcription_id": request.transcription_id,
        "recipients": request.recipients,
        "sent_at": result["sent_at"].isoformat(),
        "status": "sent",
    }


class CreateReminderRequest(BaseModel):
    transcription_id: str
    action_item_id: str
    remind_at: datetime
    recipients: List[str]


@router.post("/followup/reminder")
async def create_action_item_reminder(
    request: CreateReminderRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """アクションアイテムのリマインダーを作成"""
    reminder = await meeting_followup_manager.create_reminder(
        tenant_id=tenant_id,
        transcription_id=request.transcription_id,
        action_item_id=request.action_item_id,
        remind_at=request.remind_at,
        recipients=request.recipients,
    )

    return {
        "id": reminder["id"],
        "action_item_id": reminder["action_item_id"],
        "remind_at": reminder["remind_at"].isoformat(),
        "recipients": reminder["recipients"],
        "status": "scheduled",
    }


@router.get("/followup/reminders")
async def list_reminders(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """リマインダー一覧"""
    reminders = list(meeting_followup_manager._reminders.values())

    return {
        "reminders": [
            {
                "id": r["id"],
                "action_item_id": r["action_item_id"],
                "remind_at": r["remind_at"].isoformat(),
                "recipients": r["recipients"],
                "status": r["status"],
            }
            for r in reminders
        ],
        "count": len(reminders),
    }


# =====================
# 接続状態
# =====================

@router.get("/status")
async def get_calendar_status(
    user_id: str = Depends(get_current_user_id),
):
    """カレンダー接続状態"""
    google_connected = user_id in google_calendar._credentials
    outlook_connected = user_id in outlook_calendar._credentials

    auto_recording = recording_scheduler._user_configs.get(user_id)

    return {
        "connections": {
            "google": {
                "connected": google_connected,
                "provider": "Google Calendar",
            },
            "outlook": {
                "connected": outlook_connected,
                "provider": "Outlook Calendar",
            },
        },
        "auto_recording": {
            "enabled": auto_recording is not None,
            "config": auto_recording if auto_recording else None,
        },
    }


@router.delete("/disconnect/{provider}")
async def disconnect_calendar(
    provider: str,
    user_id: str = Depends(get_current_user_id),
):
    """カレンダー接続を解除"""
    if provider == "google":
        if user_id in google_calendar._credentials:
            del google_calendar._credentials[user_id]
        return {"status": "disconnected", "provider": "google"}

    elif provider == "outlook":
        if user_id in outlook_calendar._credentials:
            del outlook_calendar._credentials[user_id]
        return {"status": "disconnected", "provider": "outlook"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
