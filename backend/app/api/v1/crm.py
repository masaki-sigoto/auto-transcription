"""CRM/プロジェクト管理連携APIエンドポイント（拡張版）"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.crm_integration_service import (
    salesforce_integration,
    hubspot_integration,
    notion_integration,
    jira_integration,
    asana_integration,
    integration_manager,
    CRMPlatform,
    ProjectPlatform,
)

router = APIRouter(prefix="/crm", tags=["crm"])


async def get_current_tenant_id() -> str:
    return "default-tenant"


# =====================
# Salesforce拡張
# =====================

@router.get("/salesforce/auth/url")
async def get_salesforce_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Salesforce OAuth認証URL"""
    auth_url = salesforce_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )
    return {"auth_url": auth_url, "platform": "salesforce"}


class SalesforceCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/salesforce/auth/callback")
async def salesforce_auth_callback(
    request: SalesforceCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforce認証コールバック"""
    try:
        credentials = await salesforce_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )
        salesforce_integration.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "platform": "salesforce",
            "instance_url": credentials.instance_url,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/salesforce/auth/status")
async def get_salesforce_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforce認証ステータス"""
    credentials = salesforce_integration.get_credentials(tenant_id)
    return {
        "authenticated": credentials is not None,
        "platform": "salesforce",
        "instance_url": credentials.instance_url if credentials else None,
    }


class SalesforceNoteRequest(BaseModel):
    title: str
    content: str
    transcription_id: Optional[str] = None


@router.post("/salesforce/opportunities/{opportunity_id}/notes")
async def create_salesforce_note(
    opportunity_id: str,
    request: SalesforceNoteRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforce商談にメモを追加"""
    try:
        note = await salesforce_integration.create_opportunity_note(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            title=request.title,
            content=request.content,
            transcription_id=request.transcription_id,
        )
        return note
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SalesforceTaskRequest(BaseModel):
    subject: str
    description: str
    related_to_id: Optional[str] = None
    due_date: Optional[datetime] = None
    assigned_to_id: Optional[str] = None


@router.post("/salesforce/tasks")
async def create_salesforce_task(
    request: SalesforceTaskRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforceタスクを作成"""
    try:
        task = await salesforce_integration.create_task(
            tenant_id=tenant_id,
            subject=request.subject,
            description=request.description,
            related_to_id=request.related_to_id,
            due_date=request.due_date,
            assigned_to_id=request.assigned_to_id,
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SalesforceCallLogRequest(BaseModel):
    related_to_id: str
    subject: str
    description: str
    duration_minutes: int
    transcription_link: Optional[str] = None


@router.post("/salesforce/calls")
async def log_salesforce_call(
    request: SalesforceCallLogRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforce通話ログを記録"""
    try:
        call = await salesforce_integration.log_call(
            tenant_id=tenant_id,
            related_to_id=request.related_to_id,
            subject=request.subject,
            description=request.description,
            duration_minutes=request.duration_minutes,
            transcription_link=request.transcription_link,
        )
        return call
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/salesforce/opportunities/search")
async def search_salesforce_opportunities(
    query: str,
    limit: int = Query(default=10, le=50),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Salesforce商談を検索"""
    try:
        opportunities = await salesforce_integration.search_opportunities(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
        )
        return {"opportunities": opportunities, "count": len(opportunities)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# HubSpot拡張
# =====================

@router.get("/hubspot/auth/url")
async def get_hubspot_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """HubSpot OAuth認証URL"""
    auth_url = hubspot_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )
    return {"auth_url": auth_url, "platform": "hubspot"}


class HubSpotCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/hubspot/auth/callback")
async def hubspot_auth_callback(
    request: HubSpotCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """HubSpot認証コールバック"""
    try:
        credentials = await hubspot_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )
        hubspot_integration.store_credentials(tenant_id, credentials)

        return {"status": "authenticated", "platform": "hubspot"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hubspot/auth/status")
async def get_hubspot_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """HubSpot認証ステータス"""
    credentials = hubspot_integration.get_credentials(tenant_id)
    return {
        "authenticated": credentials is not None,
        "platform": "hubspot",
    }


class HubSpotNoteRequest(BaseModel):
    content: str
    associated_object_type: str
    associated_object_id: str


@router.post("/hubspot/notes")
async def create_hubspot_note(
    request: HubSpotNoteRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """HubSpotノートを作成"""
    try:
        note = await hubspot_integration.create_note(
            tenant_id=tenant_id,
            content=request.content,
            associated_object_type=request.associated_object_type,
            associated_object_id=request.associated_object_id,
        )
        return note
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class HubSpotMeetingRequest(BaseModel):
    title: str
    body: str
    start_time: datetime
    end_time: datetime
    associated_contact_ids: List[str] = []
    transcription_content: Optional[str] = None


@router.post("/hubspot/meetings")
async def log_hubspot_meeting(
    request: HubSpotMeetingRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """HubSpotミーティングをログ"""
    try:
        meeting = await hubspot_integration.log_meeting(
            tenant_id=tenant_id,
            title=request.title,
            body=request.body,
            start_time=request.start_time,
            end_time=request.end_time,
            associated_contact_ids=request.associated_contact_ids,
            transcription_content=request.transcription_content,
        )
        return meeting
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# Notion拡張
# =====================

@router.get("/notion/auth/url")
async def get_notion_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Notion OAuth認証URL"""
    auth_url = notion_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )
    return {"auth_url": auth_url, "platform": "notion"}


class NotionCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/notion/auth/callback")
async def notion_auth_callback(
    request: NotionCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Notion認証コールバック"""
    try:
        credentials = await notion_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )
        notion_integration.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "platform": "notion",
            "workspace_id": credentials.workspace_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/notion/auth/status")
async def get_notion_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Notion認証ステータス"""
    credentials = notion_integration.get_credentials(tenant_id)
    return {
        "authenticated": credentials is not None,
        "platform": "notion",
        "workspace_id": credentials.workspace_id if credentials else None,
    }


@router.get("/notion/databases")
async def list_notion_databases(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Notionデータベース一覧"""
    try:
        databases = await notion_integration.list_databases(tenant_id)
        return {"databases": databases, "count": len(databases)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class NotionPageRequest(BaseModel):
    parent_id: str
    title: str
    content: str
    properties: Optional[dict] = None


@router.post("/notion/pages")
async def create_notion_page(
    request: NotionPageRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Notionページを作成"""
    try:
        page = await notion_integration.create_page(
            tenant_id=tenant_id,
            parent_id=request.parent_id,
            title=request.title,
            content=request.content,
            properties=request.properties,
        )
        return page
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class NotionMeetingNotesRequest(BaseModel):
    database_id: str
    meeting_title: str
    date: datetime
    attendees: List[str]
    transcription: str
    summary: str
    action_items: List[dict]


@router.post("/notion/meeting-notes")
async def create_notion_meeting_notes(
    request: NotionMeetingNotesRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Notion会議ノートを作成"""
    try:
        page = await notion_integration.create_meeting_notes_page(
            tenant_id=tenant_id,
            database_id=request.database_id,
            meeting_title=request.meeting_title,
            date=request.date,
            attendees=request.attendees,
            transcription=request.transcription,
            summary=request.summary,
            action_items=request.action_items,
        )
        return page
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# Jira拡張
# =====================

@router.get("/jira/auth/url")
async def get_jira_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Jira OAuth認証URL"""
    auth_url = jira_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )
    return {"auth_url": auth_url, "platform": "jira"}


class JiraCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/jira/auth/callback")
async def jira_auth_callback(
    request: JiraCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Jira認証コールバック"""
    try:
        credentials = await jira_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )
        jira_integration.store_credentials(tenant_id, credentials)

        return {"status": "authenticated", "platform": "jira"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jira/auth/status")
async def get_jira_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Jira認証ステータス"""
    credentials = jira_integration.get_credentials(tenant_id)
    return {
        "authenticated": credentials is not None,
        "platform": "jira",
    }


@router.get("/jira/projects")
async def list_jira_projects(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Jiraプロジェクト一覧"""
    try:
        projects = await jira_integration.list_projects(tenant_id)
        return {"projects": projects, "count": len(projects)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class JiraIssueRequest(BaseModel):
    project_key: str
    issue_type: str = "Task"
    summary: str
    description: str
    assignee_id: Optional[str] = None
    priority: str = "Medium"
    labels: List[str] = []
    due_date: Optional[datetime] = None


@router.post("/jira/issues")
async def create_jira_issue(
    request: JiraIssueRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Jira課題を作成"""
    try:
        issue = await jira_integration.create_issue(
            tenant_id=tenant_id,
            project_key=request.project_key,
            issue_type=request.issue_type,
            summary=request.summary,
            description=request.description,
            assignee_id=request.assignee_id,
            priority=request.priority,
            labels=request.labels,
            due_date=request.due_date,
        )
        return {
            "id": issue.id,
            "title": issue.title,
            "status": issue.status,
            "priority": issue.priority,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class JiraActionItemsRequest(BaseModel):
    project_key: str
    action_items: List[dict]
    meeting_reference: Optional[str] = None


@router.post("/jira/issues/from-action-items")
async def create_jira_issues_from_action_items(
    request: JiraActionItemsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """アクションアイテムからJira課題を一括作成"""
    try:
        issues = await jira_integration.create_issues_from_action_items(
            tenant_id=tenant_id,
            project_key=request.project_key,
            action_items=request.action_items,
            meeting_reference=request.meeting_reference,
        )
        return {
            "issues": [
                {"id": i.id, "title": i.title, "status": i.status}
                for i in issues
            ],
            "count": len(issues),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# Asana拡張
# =====================

@router.get("/asana/auth/url")
async def get_asana_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Asana OAuth認証URL"""
    auth_url = asana_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )
    return {"auth_url": auth_url, "platform": "asana"}


class AsanaCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/asana/auth/callback")
async def asana_auth_callback(
    request: AsanaCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Asana認証コールバック"""
    try:
        credentials = await asana_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )
        asana_integration.store_credentials(tenant_id, credentials)

        return {"status": "authenticated", "platform": "asana"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/asana/auth/status")
async def get_asana_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Asana認証ステータス"""
    credentials = asana_integration.get_credentials(tenant_id)
    return {
        "authenticated": credentials is not None,
        "platform": "asana",
    }


@router.get("/asana/workspaces")
async def list_asana_workspaces(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Asanaワークスペース一覧"""
    try:
        workspaces = await asana_integration.list_workspaces(tenant_id)
        return {"workspaces": workspaces, "count": len(workspaces)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/asana/workspaces/{workspace_id}/projects")
async def list_asana_projects(
    workspace_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Asanaプロジェクト一覧"""
    try:
        projects = await asana_integration.list_projects(tenant_id, workspace_id)
        return {"projects": projects, "count": len(projects)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AsanaTaskRequest(BaseModel):
    project_id: str
    name: str
    notes: str
    assignee_id: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: List[str] = []


@router.post("/asana/tasks")
async def create_asana_task(
    request: AsanaTaskRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Asanaタスクを作成"""
    try:
        task = await asana_integration.create_task(
            tenant_id=tenant_id,
            project_id=request.project_id,
            name=request.name,
            notes=request.notes,
            assignee_id=request.assignee_id,
            due_date=request.due_date,
            tags=request.tags,
        )
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AsanaActionItemsRequest(BaseModel):
    project_id: str
    action_items: List[dict]
    meeting_reference: Optional[str] = None


@router.post("/asana/tasks/from-action-items")
async def create_asana_tasks_from_action_items(
    request: AsanaActionItemsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """アクションアイテムからAsanaタスクを一括作成"""
    try:
        tasks = await asana_integration.create_tasks_from_action_items(
            tenant_id=tenant_id,
            project_id=request.project_id,
            action_items=request.action_items,
            meeting_reference=request.meeting_reference,
        )
        return {
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status}
                for t in tasks
            ],
            "count": len(tasks),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# 統合同期
# =====================

class SyncTranscriptionRequest(BaseModel):
    transcription_id: str
    platform: str
    related_record_id: Optional[str] = None


@router.post("/sync/transcription")
async def sync_transcription_to_crm(
    request: SyncTranscriptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こしをCRMに同期"""
    # 実際はDBから取得
    transcription_data = {
        "id": request.transcription_id,
        "title": "会議の文字起こし",
        "segments": [
            {"speaker_id": "話者1", "text": "サンプルテキスト"},
        ],
    }

    try:
        crm_platform = CRMPlatform(request.platform)
        result = await integration_manager.sync_transcription_to_crm(
            tenant_id=tenant_id,
            transcription_data=transcription_data,
            crm_platform=crm_platform,
            related_record_id=request.related_record_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CreateTasksRequest(BaseModel):
    action_items: List[dict]
    platform: str
    project_id: str
    meeting_reference: Optional[str] = None


@router.post("/sync/action-items")
async def create_tasks_from_action_items(
    request: CreateTasksRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """アクションアイテムからタスクを作成"""
    try:
        platform = ProjectPlatform(request.platform)
        tasks = await integration_manager.create_tasks_from_action_items(
            tenant_id=tenant_id,
            action_items=request.action_items,
            platform=platform,
            project_id=request.project_id,
            meeting_reference=request.meeting_reference,
        )
        return {
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status}
                for t in tasks
            ],
            "count": len(tasks),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# プラットフォーム情報
# =====================

@router.get("/platforms")
async def list_crm_platforms():
    """CRM/プロジェクト管理プラットフォーム一覧"""
    return {
        "crm": [
            {
                "id": "salesforce",
                "name": "Salesforce",
                "description": "商談メモ・タスク・通話ログの自動登録",
                "features": ["商談メモ", "タスク作成", "通話ログ", "商談検索"],
            },
            {
                "id": "hubspot",
                "name": "HubSpot",
                "description": "ノート・タスク・ミーティングログの自動登録",
                "features": ["ノート作成", "タスク作成", "ミーティングログ"],
            },
        ],
        "project_management": [
            {
                "id": "notion",
                "name": "Notion",
                "description": "会議ノートページの自動作成",
                "features": ["ページ作成", "会議ノート", "データベース連携"],
            },
            {
                "id": "jira",
                "name": "Jira",
                "description": "アクションアイテムからの課題自動作成",
                "features": ["課題作成", "一括作成", "ラベル付け"],
            },
            {
                "id": "asana",
                "name": "Asana",
                "description": "アクションアイテムからのタスク自動作成",
                "features": ["タスク作成", "一括作成", "タグ付け"],
            },
        ],
    }
