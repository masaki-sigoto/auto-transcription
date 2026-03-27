import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import get_settings
from app.models.webhook import Integration
from app.services.transcription_service import TranscriptionService
from app.services.video_meeting_service import (
    VideoMeetingIntegrationService,
    ZoomService,
    TeamsService,
    GoogleMeetService,
    MeetingInfo,
)
from app.services.crm_service import (
    CRMIntegrationService,
    SalesforceService,
    HubSpotService,
    CRMContact,
    CRMDeal,
    CRMActivity,
)
from app.services.project_management_service import (
    ProjectManagementService,
    JiraService,
    AsanaService,
    NotionService,
    Project,
    ProjectTask,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

settings = get_settings()


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    service: str
    is_active: bool
    config: dict
    created_at: str


class NotionExportRequest(BaseModel):
    transcription_id: uuid.UUID
    database_id: str
    include_minutes: bool = True


class SlackPostRequest(BaseModel):
    transcription_id: uuid.UUID
    channel: str
    include_minutes: bool = True
    upload_file: bool = False


# =============================================================================
# 連携一覧・管理
# =============================================================================

@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """連携一覧を取得"""
    query = select(Integration).where(Integration.user_id == user_id)
    result = await db.execute(query)
    integrations = result.scalars().all()

    return [
        IntegrationResponse(
            id=i.id,
            service=i.service,
            is_active=i.is_active,
            config=i.config,
            created_at=i.created_at.isoformat(),
        )
        for i in integrations
    ]


@router.delete("/{integration_id}", status_code=204)
async def disconnect_integration(
    integration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """連携を解除"""
    query = select(Integration).where(
        Integration.id == integration_id,
        Integration.user_id == user_id,
    )
    result = await db.execute(query)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)


# =============================================================================
# Notion連携
# =============================================================================

@router.get("/notion/auth")
async def notion_auth_redirect(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Notion OAuth認証へリダイレクト"""
    # TODO: 実際のOAuth実装
    client_id = settings.notion_client_id if hasattr(settings, 'notion_client_id') else ""
    redirect_uri = f"{settings.app_url}/api/v1/integrations/notion/callback"

    auth_url = (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&owner=user"
        f"&redirect_uri={redirect_uri}"
    )

    return {"auth_url": auth_url}


@router.get("/notion/callback")
async def notion_auth_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Notion OAuth コールバック"""
    import httpx

    client_id = settings.notion_client_id if hasattr(settings, 'notion_client_id') else ""
    client_secret = settings.notion_client_secret if hasattr(settings, 'notion_client_secret') else ""
    redirect_uri = f"{settings.app_url}/api/v1/integrations/notion/callback"

    # トークン交換
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            auth=(client_id, client_secret),
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="OAuth token exchange failed")

        token_data = response.json()

    # 連携を保存
    integration = Integration(
        user_id=user_id,
        service="notion",
        access_token=token_data["access_token"],
        config={
            "workspace_name": token_data.get("workspace_name"),
            "workspace_id": token_data.get("workspace_id"),
        },
    )
    db.add(integration)

    return {"message": "Notion connected successfully"}


@router.get("/notion/databases")
async def list_notion_databases(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Notionデータベース一覧を取得"""
    from app.services.integrations.notion import NotionClient

    # 連携を取得
    query = select(Integration).where(
        Integration.user_id == user_id,
        Integration.service == "notion",
        Integration.is_active == True,
    )
    result = await db.execute(query)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Notion not connected")

    client = NotionClient(integration.access_token)
    databases = await client.search_databases()

    return [
        {
            "id": d["id"],
            "title": d.get("title", [{}])[0].get("plain_text", "Untitled") if d.get("title") else "Untitled",
        }
        for d in databases
    ]


@router.post("/notion/export")
async def export_to_notion(
    request: NotionExportRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしをNotionにエクスポート"""
    from app.services.integrations.notion import export_to_notion as notion_export
    from app.services.ai_summary import AISummaryService
    from app.services.transcription_engine import TranscriptionSegment

    # 連携を取得
    query = select(Integration).where(
        Integration.user_id == user_id,
        Integration.service == "notion",
        Integration.is_active == True,
    )
    result = await db.execute(query)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Notion not connected")

    # 文字起こしを取得
    service = TranscriptionService(db)
    transcription = await service.get_by_id(request.transcription_id, user_id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    # 話者マップ
    speaker_map = {str(s.id): s.label for s in transcription.speakers}

    # セグメントデータ
    segments_data = [
        {
            "start_time_ms": s.start_time_ms,
            "end_time_ms": s.end_time_ms,
            "text": s.text,
            "speaker_label": speaker_map.get(str(s.speaker_id)) if s.speaker_id else None,
        }
        for s in transcription.segments
    ]

    # 議事録生成（オプション）
    meeting_minutes = None
    if request.include_minutes:
        ai_service = AISummaryService()
        segments = [
            TranscriptionSegment(
                start_time_ms=s.start_time_ms,
                end_time_ms=s.end_time_ms,
                text=s.text,
                speaker_id=speaker_map.get(str(s.speaker_id)) if s.speaker_id else None,
            )
            for s in transcription.segments
        ]
        minutes = await ai_service.generate_meeting_minutes(segments)
        meeting_minutes = {
            "participants": minutes.participants,
            "agenda_items": minutes.agenda_items,
            "action_items": minutes.action_items,
            "next_steps": minutes.next_steps,
        }

    # Notionにエクスポート
    page = await notion_export(
        access_token=integration.access_token,
        database_id=request.database_id,
        title=transcription.title or "無題の文字起こし",
        summary=transcription.summary or "",
        segments=segments_data,
        meeting_minutes=meeting_minutes,
    )

    return {
        "page_id": page.get("id"),
        "url": page.get("url"),
    }


# =============================================================================
# Slack連携
# =============================================================================

@router.get("/slack/auth")
async def slack_auth_redirect(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Slack OAuth認証へリダイレクト"""
    client_id = settings.slack_client_id if hasattr(settings, 'slack_client_id') else ""
    redirect_uri = f"{settings.app_url}/api/v1/integrations/slack/callback"
    scopes = "channels:read,chat:write,files:write"

    auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
    )

    return {"auth_url": auth_url}


@router.get("/slack/callback")
async def slack_auth_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Slack OAuth コールバック"""
    import httpx

    client_id = settings.slack_client_id if hasattr(settings, 'slack_client_id') else ""
    client_secret = settings.slack_client_secret if hasattr(settings, 'slack_client_secret') else ""
    redirect_uri = f"{settings.app_url}/api/v1/integrations/slack/callback"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

        token_data = response.json()

        if not token_data.get("ok"):
            raise HTTPException(status_code=400, detail=token_data.get("error"))

    # 連携を保存
    integration = Integration(
        user_id=user_id,
        service="slack",
        access_token=token_data["access_token"],
        config={
            "team_name": token_data.get("team", {}).get("name"),
            "team_id": token_data.get("team", {}).get("id"),
        },
    )
    db.add(integration)

    return {"message": "Slack connected successfully"}


@router.get("/slack/channels")
async def list_slack_channels(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Slackチャンネル一覧を取得"""
    from app.services.integrations.slack import SlackClient

    query = select(Integration).where(
        Integration.user_id == user_id,
        Integration.service == "slack",
        Integration.is_active == True,
    )
    result = await db.execute(query)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack not connected")

    client = SlackClient(integration.access_token)
    channels = await client.list_channels()

    return [
        {"id": c["id"], "name": c["name"]}
        for c in channels
    ]


@router.post("/slack/post")
async def post_to_slack(
    request: SlackPostRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしをSlackに投稿"""
    from app.services.integrations.slack import (
        post_transcription_to_slack,
        upload_transcript_file,
    )
    from app.services.ai_summary import AISummaryService
    from app.services.transcription_engine import TranscriptionSegment

    query = select(Integration).where(
        Integration.user_id == user_id,
        Integration.service == "slack",
        Integration.is_active == True,
    )
    result = await db.execute(query)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack not connected")

    # 文字起こしを取得
    service = TranscriptionService(db)
    transcription = await service.get_by_id(request.transcription_id, user_id)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    # 議事録生成（オプション）
    meeting_minutes = None
    if request.include_minutes:
        speaker_map = {str(s.id): s.label for s in transcription.speakers}
        ai_service = AISummaryService()
        segments = [
            TranscriptionSegment(
                start_time_ms=s.start_time_ms,
                end_time_ms=s.end_time_ms,
                text=s.text,
                speaker_id=speaker_map.get(str(s.speaker_id)) if s.speaker_id else None,
            )
            for s in transcription.segments
        ]
        minutes = await ai_service.generate_meeting_minutes(segments)
        meeting_minutes = {
            "action_items": minutes.action_items,
            "next_steps": minutes.next_steps,
        }

    # 投稿
    transcription_url = f"{settings.app_url}/transcriptions/{transcription.id}"

    message = await post_transcription_to_slack(
        access_token=integration.access_token,
        channel=request.channel,
        title=transcription.title or "無題の文字起こし",
        summary=transcription.summary or "要約なし",
        duration_sec=transcription.audio_duration_sec or 0,
        transcription_url=transcription_url,
        meeting_minutes=meeting_minutes,
    )

    # ファイルアップロード（オプション）
    file_result = None
    if request.upload_file:
        transcript_text = "\n".join(
            f"[{s.start_time_ms // 60000}:{(s.start_time_ms // 1000) % 60:02d}] {s.text}"
            for s in transcription.segments
        )
        file_result = await upload_transcript_file(
            access_token=integration.access_token,
            channel=request.channel,
            title=transcription.title or "文字起こし",
            transcript_text=transcript_text,
        )

    return {
        "message_ts": message.get("ts"),
        "file_id": file_result.get("file", {}).get("id") if file_result else None,
    }


# =============================================================================
# ビデオ会議連携
# =============================================================================

class VideoMeetingCredentials(BaseModel):
    provider: str  # zoom, teams, meet
    access_token: str


class ImportRecordingRequest(BaseModel):
    provider: str
    meeting_id: str
    access_token: str


@router.get("/video-meetings", response_model=List[MeetingInfo])
async def get_video_meetings(
    provider: str,
    access_token: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ビデオ会議一覧を取得"""
    if provider == "zoom":
        service = ZoomService(access_token)
    elif provider == "teams":
        service = TeamsService(access_token)
    elif provider == "meet":
        service = GoogleMeetService(access_token)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    try:
        meetings = await service.get_meetings(from_date=from_date, to_date=to_date)
        return meetings
    finally:
        await service.close()


@router.post("/video-meetings/import")
async def import_video_recording(
    request: ImportRecordingRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ビデオ会議録画をインポート"""
    service = VideoMeetingIntegrationService(db)

    result = await service.import_recording(
        provider=request.provider,
        meeting_id=request.meeting_id,
        access_token=request.access_token,
    )

    return result


@router.get("/video-meetings/recordings")
async def get_video_recordings(
    provider: str,
    access_token: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ビデオ会議録画一覧を取得（Zoomのみ）"""
    if provider != "zoom":
        raise HTTPException(status_code=400, detail="Only Zoom recordings are supported")

    service = ZoomService(access_token)
    try:
        recordings = await service.get_recordings(from_date=from_date, to_date=to_date)
        return recordings
    finally:
        await service.close()


# =============================================================================
# CRM連携
# =============================================================================

class ExportToCRMRequest(BaseModel):
    provider: str
    access_token: str
    instance_url: Optional[str] = None
    transcription_id: str
    title: str
    summary: str
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None


@router.get("/crm/contacts", response_model=List[CRMContact])
async def get_crm_contacts(
    provider: str,
    access_token: str,
    instance_url: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """CRM連絡先を取得"""
    if provider == "salesforce":
        if not instance_url:
            raise HTTPException(status_code=400, detail="instance_url is required for Salesforce")
        service = SalesforceService(access_token, instance_url)
    elif provider == "hubspot":
        service = HubSpotService(access_token)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported CRM provider: {provider}")

    try:
        contacts = await service.get_contacts(search=search, limit=limit)
        return contacts
    finally:
        await service.close()


@router.get("/crm/deals", response_model=List[CRMDeal])
async def get_crm_deals(
    provider: str,
    access_token: str,
    instance_url: Optional[str] = None,
    contact_id: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = Query(50, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """CRM商談を取得"""
    if provider == "salesforce":
        if not instance_url:
            raise HTTPException(status_code=400, detail="instance_url is required for Salesforce")
        service = SalesforceService(access_token, instance_url)
    elif provider == "hubspot":
        service = HubSpotService(access_token)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported CRM provider: {provider}")

    try:
        deals = await service.get_deals(contact_id=contact_id, stage=stage, limit=limit)
        return deals
    finally:
        await service.close()


@router.post("/crm/export", response_model=CRMActivity)
async def export_to_crm(
    request: ExportToCRMRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしをCRMにエクスポート"""
    service = CRMIntegrationService(db)

    activity = await service.export_to_crm(
        provider=request.provider,
        access_token=request.access_token,
        transcription_id=request.transcription_id,
        title=request.title,
        summary=request.summary,
        contact_id=request.contact_id,
        deal_id=request.deal_id,
        instance_url=request.instance_url,
    )

    return activity


# =============================================================================
# プロジェクト管理連携
# =============================================================================

class ExportActionItemsRequest(BaseModel):
    provider: str
    credentials: dict
    project_id: str
    action_items: List[dict]


class ExportMeetingNotesRequest(BaseModel):
    provider: str
    credentials: dict
    project_id: str
    title: str
    summary: str
    action_items: List[dict]
    participants: List[str]


@router.get("/projects", response_model=List[Project])
async def get_projects(
    provider: str,
    access_token: Optional[str] = None,
    email: Optional[str] = None,
    api_token: Optional[str] = None,
    domain: Optional[str] = None,
    workspace_id: Optional[str] = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """プロジェクト一覧を取得"""
    if provider == "jira":
        if not all([email, api_token, domain]):
            raise HTTPException(
                status_code=400,
                detail="email, api_token, and domain are required for Jira",
            )
        service = JiraService(email, api_token, domain)
        try:
            projects = await service.get_projects()
            return projects
        finally:
            await service.close()

    elif provider == "asana":
        if not access_token:
            raise HTTPException(status_code=400, detail="access_token is required for Asana")
        service = AsanaService(access_token)
        try:
            if not workspace_id:
                workspaces = await service.get_workspaces()
                if not workspaces:
                    return []
                workspace_id = workspaces[0]["gid"]

            projects = await service.get_projects(workspace_id)
            return projects
        finally:
            await service.close()

    elif provider == "notion":
        if not access_token:
            raise HTTPException(status_code=400, detail="access_token is required for Notion")
        service = NotionService(access_token)
        try:
            databases = await service.get_databases()
            return databases
        finally:
            await service.close()

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


@router.get("/projects/{project_id}/tasks", response_model=List[ProjectTask])
async def get_project_tasks(
    project_id: str,
    provider: str,
    access_token: Optional[str] = None,
    email: Optional[str] = None,
    api_token: Optional[str] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """プロジェクトタスク一覧を取得"""
    if provider == "jira":
        if not all([email, api_token, domain]):
            raise HTTPException(
                status_code=400,
                detail="email, api_token, and domain are required for Jira",
            )
        service = JiraService(email, api_token, domain)
        try:
            tasks = await service.get_tasks(project_id, status=status, limit=limit)
            return tasks
        finally:
            await service.close()

    elif provider == "asana":
        if not access_token:
            raise HTTPException(status_code=400, detail="access_token is required for Asana")
        service = AsanaService(access_token)
        try:
            completed = None
            if status == "completed":
                completed = True
            elif status == "pending":
                completed = False

            tasks = await service.get_tasks(project_id, completed=completed, limit=limit)
            return tasks
        finally:
            await service.close()

    elif provider == "notion":
        if not access_token:
            raise HTTPException(status_code=400, detail="access_token is required for Notion")
        service = NotionService(access_token)
        try:
            tasks = await service.get_pages(project_id, limit=limit)
            return tasks
        finally:
            await service.close()

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


@router.post("/projects/export-action-items", response_model=List[ProjectTask])
async def export_action_items_to_project(
    request: ExportActionItemsRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アクションアイテムをプロジェクトにエクスポート"""
    service = ProjectManagementService(db)

    tasks = await service.export_action_items(
        provider=request.provider,
        credentials=request.credentials,
        project_id=request.project_id,
        action_items=request.action_items,
    )

    return tasks


@router.post("/projects/export-meeting-notes")
async def export_meeting_notes_to_project(
    request: ExportMeetingNotesRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """会議議事録をプロジェクトにエクスポート"""
    service = ProjectManagementService(db)

    page_id = await service.export_meeting_notes(
        provider=request.provider,
        credentials=request.credentials,
        project_id=request.project_id,
        title=request.title,
        summary=request.summary,
        action_items=request.action_items,
        participants=request.participants,
    )

    return {"page_id": page_id, "status": "created"}
