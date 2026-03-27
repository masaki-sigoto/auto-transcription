"""CRM/プロジェクト管理連携サービス"""

import os
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class CRMPlatform(str, Enum):
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"
    ZOHO = "zoho"


class ProjectPlatform(str, Enum):
    NOTION = "notion"
    JIRA = "jira"
    ASANA = "asana"
    TRELLO = "trello"
    MONDAY = "monday"


@dataclass
class CRMCredentials:
    """CRM認証情報"""
    platform: CRMPlatform
    access_token: str
    refresh_token: Optional[str] = None
    instance_url: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass
class ProjectCredentials:
    """プロジェクト管理認証情報"""
    platform: ProjectPlatform
    access_token: str
    refresh_token: Optional[str] = None
    workspace_id: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass
class CRMRecord:
    """CRMレコード"""
    id: str
    type: str  # opportunity, account, contact, lead
    name: str
    fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class ProjectTask:
    """プロジェクトタスク"""
    id: str
    title: str
    description: str
    status: str
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "medium"
    labels: List[str] = field(default_factory=list)


# =====================
# Salesforce連携
# =====================

class SalesforceIntegration:
    """Salesforce連携"""

    def __init__(self):
        self.client_id = os.getenv("SALESFORCE_CLIENT_ID", "")
        self.client_secret = os.getenv("SALESFORCE_CLIENT_SECRET", "")
        self._credentials: Dict[str, CRMCredentials] = {}
        self._records: Dict[str, CRMRecord] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        auth_url = (
            f"https://login.salesforce.com/services/oauth2/authorize?"
            f"response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> CRMCredentials:
        """認証コードをトークンに交換"""
        # シミュレーション
        return CRMCredentials(
            platform=CRMPlatform.SALESFORCE,
            access_token=f"sf_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
            instance_url="https://example.my.salesforce.com",
            expires_at=datetime.utcnow(),
        )

    def store_credentials(self, tenant_id: str, credentials: CRMCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[CRMCredentials]:
        return self._credentials.get(tenant_id)

    async def create_opportunity_note(
        self,
        tenant_id: str,
        opportunity_id: str,
        title: str,
        content: str,
        transcription_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """商談にメモを追加"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Salesforce")

        note_id = str(uuid.uuid4())

        return {
            "id": note_id,
            "opportunity_id": opportunity_id,
            "title": title,
            "content": content[:32000],  # Salesforce制限
            "transcription_id": transcription_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    async def create_task(
        self,
        tenant_id: str,
        subject: str,
        description: str,
        related_to_id: Optional[str] = None,
        due_date: Optional[datetime] = None,
        assigned_to_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """タスクを作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Salesforce")

        task_id = str(uuid.uuid4())

        return {
            "id": task_id,
            "subject": subject,
            "description": description,
            "related_to_id": related_to_id,
            "due_date": due_date.isoformat() if due_date else None,
            "assigned_to_id": assigned_to_id,
            "status": "Not Started",
        }

    async def search_opportunities(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """商談を検索"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Salesforce")

        # シミュレーション
        return [
            {
                "id": "opp1",
                "name": f"商談 - {query}",
                "amount": 1000000,
                "stage": "Negotiation",
                "close_date": "2024-03-31",
            }
        ]

    async def log_call(
        self,
        tenant_id: str,
        related_to_id: str,
        subject: str,
        description: str,
        duration_minutes: int,
        transcription_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通話ログを記録"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Salesforce")

        return {
            "id": str(uuid.uuid4()),
            "type": "Call",
            "subject": subject,
            "description": description,
            "duration_minutes": duration_minutes,
            "related_to_id": related_to_id,
            "transcription_link": transcription_link,
            "created_at": datetime.utcnow().isoformat(),
        }


# =====================
# HubSpot連携
# =====================

class HubSpotIntegration:
    """HubSpot連携"""

    def __init__(self):
        self.client_id = os.getenv("HUBSPOT_CLIENT_ID", "")
        self.client_secret = os.getenv("HUBSPOT_CLIENT_SECRET", "")
        self._credentials: Dict[str, CRMCredentials] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or [
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
        ]

        scope_str = "%20".join(scopes)
        auth_url = (
            f"https://app.hubspot.com/oauth/authorize?"
            f"client_id={self.client_id}"
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
    ) -> CRMCredentials:
        """認証コードをトークンに交換"""
        return CRMCredentials(
            platform=CRMPlatform.HUBSPOT,
            access_token=f"hubspot_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
        )

    def store_credentials(self, tenant_id: str, credentials: CRMCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[CRMCredentials]:
        return self._credentials.get(tenant_id)

    async def create_note(
        self,
        tenant_id: str,
        content: str,
        associated_object_type: str,
        associated_object_id: str,
    ) -> Dict[str, Any]:
        """ノートを作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with HubSpot")

        return {
            "id": str(uuid.uuid4()),
            "content": content,
            "associated_object_type": associated_object_type,
            "associated_object_id": associated_object_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    async def create_task(
        self,
        tenant_id: str,
        subject: str,
        body: str,
        due_date: Optional[datetime] = None,
        associated_deal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """タスクを作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with HubSpot")

        return {
            "id": str(uuid.uuid4()),
            "subject": subject,
            "body": body,
            "due_date": due_date.isoformat() if due_date else None,
            "associated_deal_id": associated_deal_id,
            "status": "NOT_STARTED",
        }

    async def log_meeting(
        self,
        tenant_id: str,
        title: str,
        body: str,
        start_time: datetime,
        end_time: datetime,
        associated_contact_ids: List[str] = None,
        transcription_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """ミーティングをログ"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with HubSpot")

        return {
            "id": str(uuid.uuid4()),
            "title": title,
            "body": body,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "associated_contact_ids": associated_contact_ids or [],
            "has_transcription": transcription_content is not None,
        }


# =====================
# Notion連携
# =====================

class NotionIntegration:
    """Notion連携"""

    def __init__(self):
        self.client_id = os.getenv("NOTION_CLIENT_ID", "")
        self.client_secret = os.getenv("NOTION_CLIENT_SECRET", "")
        self._credentials: Dict[str, ProjectCredentials] = {}
        self._pages: Dict[str, Dict] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        auth_url = (
            f"https://api.notion.com/v1/oauth/authorize?"
            f"client_id={self.client_id}"
            f"&response_type=code"
            f"&owner=user"
            f"&redirect_uri={redirect_uri}"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> ProjectCredentials:
        """認証コードをトークンに交換"""
        return ProjectCredentials(
            platform=ProjectPlatform.NOTION,
            access_token=f"notion_{uuid.uuid4().hex[:30]}",
            workspace_id=f"workspace_{uuid.uuid4().hex[:8]}",
        )

    def store_credentials(self, tenant_id: str, credentials: ProjectCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[ProjectCredentials]:
        return self._credentials.get(tenant_id)

    async def list_databases(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """データベース一覧"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Notion")

        return [
            {"id": "db1", "title": "議事録", "icon": "📝"},
            {"id": "db2", "title": "タスク", "icon": "✅"},
            {"id": "db3", "title": "ミーティング", "icon": "📅"},
        ]

    async def create_page(
        self,
        tenant_id: str,
        parent_id: str,
        title: str,
        content: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """ページを作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Notion")

        page_id = str(uuid.uuid4())

        page = {
            "id": page_id,
            "parent_id": parent_id,
            "title": title,
            "content": content,
            "properties": properties or {},
            "url": f"https://notion.so/{page_id.replace('-', '')}",
            "created_at": datetime.utcnow().isoformat(),
        }

        self._pages[page_id] = page
        return page

    async def create_meeting_notes_page(
        self,
        tenant_id: str,
        database_id: str,
        meeting_title: str,
        date: datetime,
        attendees: List[str],
        transcription: str,
        summary: str,
        action_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """会議ノートページを作成"""
        content = f"""# {meeting_title}

## 概要
- **日時**: {date.strftime('%Y年%m月%d日 %H:%M')}
- **参加者**: {', '.join(attendees)}

## 要約
{summary}

## アクションアイテム
"""
        for item in action_items:
            content += f"- [ ] {item.get('task', '')} (担当: {item.get('assignee', '未定')})\n"

        content += f"""
## 文字起こし
{transcription}
"""

        properties = {
            "日付": {"date": {"start": date.isoformat()}},
            "参加者": {"multi_select": [{"name": a} for a in attendees]},
            "ステータス": {"select": {"name": "完了"}},
        }

        return await self.create_page(
            tenant_id=tenant_id,
            parent_id=database_id,
            title=meeting_title,
            content=content,
            properties=properties,
        )

    async def append_to_page(
        self,
        tenant_id: str,
        page_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """ページに追記"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Notion")

        if page_id in self._pages:
            self._pages[page_id]["content"] += f"\n\n{content}"
            return self._pages[page_id]

        raise ValueError("Page not found")


# =====================
# Jira連携
# =====================

class JiraIntegration:
    """Jira連携"""

    def __init__(self):
        self.client_id = os.getenv("JIRA_CLIENT_ID", "")
        self.client_secret = os.getenv("JIRA_CLIENT_SECRET", "")
        self._credentials: Dict[str, ProjectCredentials] = {}
        self._issues: Dict[str, ProjectTask] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or [
            "read:jira-work",
            "write:jira-work",
            "read:jira-user",
        ]

        scope_str = "%20".join(scopes)
        auth_url = (
            f"https://auth.atlassian.com/authorize?"
            f"audience=api.atlassian.com"
            f"&client_id={self.client_id}"
            f"&scope={scope_str}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&prompt=consent"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> ProjectCredentials:
        """認証コードをトークンに交換"""
        return ProjectCredentials(
            platform=ProjectPlatform.JIRA,
            access_token=f"jira_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
        )

    def store_credentials(self, tenant_id: str, credentials: ProjectCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[ProjectCredentials]:
        return self._credentials.get(tenant_id)

    async def list_projects(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """プロジェクト一覧"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Jira")

        return [
            {"id": "10000", "key": "PROJ", "name": "メインプロジェクト"},
            {"id": "10001", "key": "DEV", "name": "開発"},
        ]

    async def create_issue(
        self,
        tenant_id: str,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str,
        assignee_id: Optional[str] = None,
        priority: str = "Medium",
        labels: List[str] = None,
        due_date: Optional[datetime] = None,
    ) -> ProjectTask:
        """課題を作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Jira")

        issue_id = str(uuid.uuid4())
        issue_key = f"{project_key}-{len(self._issues) + 1}"

        task = ProjectTask(
            id=issue_id,
            title=summary,
            description=description,
            status="To Do",
            assignee=assignee_id,
            due_date=due_date,
            priority=priority.lower(),
            labels=labels or [],
        )

        self._issues[issue_id] = task

        return task

    async def create_issues_from_action_items(
        self,
        tenant_id: str,
        project_key: str,
        action_items: List[Dict[str, Any]],
        meeting_reference: Optional[str] = None,
    ) -> List[ProjectTask]:
        """アクションアイテムから課題を一括作成"""
        tasks = []

        for item in action_items:
            description = item.get("task", "")
            if meeting_reference:
                description += f"\n\n---\n会議参照: {meeting_reference}"

            task = await self.create_issue(
                tenant_id=tenant_id,
                project_key=project_key,
                issue_type="Task",
                summary=item.get("task", "タスク")[:255],
                description=description,
                assignee_id=item.get("assignee_id"),
                labels=["meeting-action-item"],
            )
            tasks.append(task)

        return tasks


# =====================
# Asana連携
# =====================

class AsanaIntegration:
    """Asana連携"""

    def __init__(self):
        self.client_id = os.getenv("ASANA_CLIENT_ID", "")
        self.client_secret = os.getenv("ASANA_CLIENT_SECRET", "")
        self._credentials: Dict[str, ProjectCredentials] = {}
        self._tasks: Dict[str, ProjectTask] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        auth_url = (
            f"https://app.asana.com/-/oauth_authorize?"
            f"client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> ProjectCredentials:
        """認証コードをトークンに交換"""
        return ProjectCredentials(
            platform=ProjectPlatform.ASANA,
            access_token=f"asana_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
        )

    def store_credentials(self, tenant_id: str, credentials: ProjectCredentials):
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[ProjectCredentials]:
        return self._credentials.get(tenant_id)

    async def list_workspaces(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """ワークスペース一覧"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Asana")

        return [
            {"gid": "ws1", "name": "メインワークスペース"},
        ]

    async def list_projects(
        self,
        tenant_id: str,
        workspace_id: str,
    ) -> List[Dict[str, Any]]:
        """プロジェクト一覧"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Asana")

        return [
            {"gid": "proj1", "name": "開発タスク"},
            {"gid": "proj2", "name": "会議フォローアップ"},
        ]

    async def create_task(
        self,
        tenant_id: str,
        project_id: str,
        name: str,
        notes: str,
        assignee_id: Optional[str] = None,
        due_date: Optional[datetime] = None,
        tags: List[str] = None,
    ) -> ProjectTask:
        """タスクを作成"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Asana")

        task_id = str(uuid.uuid4())

        task = ProjectTask(
            id=task_id,
            title=name,
            description=notes,
            status="incomplete",
            assignee=assignee_id,
            due_date=due_date,
            labels=tags or [],
        )

        self._tasks[task_id] = task
        return task

    async def create_tasks_from_action_items(
        self,
        tenant_id: str,
        project_id: str,
        action_items: List[Dict[str, Any]],
        meeting_reference: Optional[str] = None,
    ) -> List[ProjectTask]:
        """アクションアイテムからタスクを一括作成"""
        tasks = []

        for item in action_items:
            notes = item.get("task", "")
            if meeting_reference:
                notes += f"\n\n---\n会議参照: {meeting_reference}"

            task = await self.create_task(
                tenant_id=tenant_id,
                project_id=project_id,
                name=item.get("task", "タスク"),
                notes=notes,
                assignee_id=item.get("assignee_id"),
                tags=["meeting-action-item"],
            )
            tasks.append(task)

        return tasks


# =====================
# 統合マネージャー
# =====================

class IntegrationManager:
    """CRM/プロジェクト管理統合マネージャー"""

    def __init__(self):
        self.salesforce = SalesforceIntegration()
        self.hubspot = HubSpotIntegration()
        self.notion = NotionIntegration()
        self.jira = JiraIntegration()
        self.asana = AsanaIntegration()
        self._auto_sync_configs: Dict[str, Dict[str, Any]] = {}

    async def setup_auto_sync(
        self,
        tenant_id: str,
        platform: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """自動同期を設定"""
        config_id = f"{tenant_id}_{platform}"

        self._auto_sync_configs[config_id] = {
            "tenant_id": tenant_id,
            "platform": platform,
            "config": config,
            "enabled": True,
            "created_at": datetime.utcnow(),
        }

        return self._auto_sync_configs[config_id]

    async def sync_transcription_to_crm(
        self,
        tenant_id: str,
        transcription_data: Dict[str, Any],
        crm_platform: CRMPlatform,
        related_record_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """文字起こしをCRMに同期"""
        title = transcription_data.get("title", "会議メモ")
        content = self._format_transcription_for_crm(transcription_data)

        if crm_platform == CRMPlatform.SALESFORCE:
            if related_record_id:
                return await self.salesforce.create_opportunity_note(
                    tenant_id=tenant_id,
                    opportunity_id=related_record_id,
                    title=title,
                    content=content,
                    transcription_id=transcription_data.get("id"),
                )
        elif crm_platform == CRMPlatform.HUBSPOT:
            return await self.hubspot.create_note(
                tenant_id=tenant_id,
                content=content,
                associated_object_type="deal" if related_record_id else "company",
                associated_object_id=related_record_id or "",
            )

        raise ValueError(f"Unsupported CRM platform: {crm_platform}")

    async def create_tasks_from_action_items(
        self,
        tenant_id: str,
        action_items: List[Dict[str, Any]],
        platform: ProjectPlatform,
        project_id: str,
        meeting_reference: Optional[str] = None,
    ) -> List[ProjectTask]:
        """アクションアイテムからタスクを作成"""
        if platform == ProjectPlatform.JIRA:
            return await self.jira.create_issues_from_action_items(
                tenant_id=tenant_id,
                project_key=project_id,
                action_items=action_items,
                meeting_reference=meeting_reference,
            )
        elif platform == ProjectPlatform.ASANA:
            return await self.asana.create_tasks_from_action_items(
                tenant_id=tenant_id,
                project_id=project_id,
                action_items=action_items,
                meeting_reference=meeting_reference,
            )

        raise ValueError(f"Unsupported project platform: {platform}")

    def _format_transcription_for_crm(
        self,
        transcription_data: Dict[str, Any],
    ) -> str:
        """CRM用に文字起こしをフォーマット"""
        lines = []
        lines.append(f"会議: {transcription_data.get('title', '不明')}")
        lines.append(f"日時: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("--- 文字起こし ---")

        for seg in transcription_data.get("segments", []):
            speaker = seg.get("speaker_id", "不明")
            text = seg.get("text", "")
            lines.append(f"{speaker}: {text}")

        return "\n".join(lines)


# グローバルインスタンス
salesforce_integration = SalesforceIntegration()
hubspot_integration = HubSpotIntegration()
notion_integration = NotionIntegration()
jira_integration = JiraIntegration()
asana_integration = AsanaIntegration()
integration_manager = IntegrationManager()
