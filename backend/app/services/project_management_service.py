"""プロジェクト管理連携サービス"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID
import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()


class ProjectTask(BaseModel):
    """タスク"""
    id: str
    title: str
    description: Optional[str]
    status: str
    priority: Optional[str]
    assignee: Optional[str]
    due_date: Optional[datetime]
    project_id: str
    provider: str  # jira, asana, notion


class Project(BaseModel):
    """プロジェクト"""
    id: str
    name: str
    description: Optional[str]
    status: Optional[str]
    provider: str


class JiraService:
    """Jira連携サービス"""

    def __init__(self, email: str, api_token: str, domain: str):
        self.email = email
        self.api_token = api_token
        self.domain = domain
        self.client = httpx.AsyncClient(
            base_url=f"https://{domain}.atlassian.net/rest/api/3",
            auth=(email, api_token),
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )

    async def get_projects(self) -> List[Project]:
        """プロジェクト一覧を取得"""
        response = await self.client.get("/project")
        response.raise_for_status()
        data = response.json()

        projects = []
        for p in data:
            projects.append(
                Project(
                    id=p["id"],
                    name=p["name"],
                    description=p.get("description"),
                    status=None,
                    provider="jira",
                )
            )

        return projects

    async def get_tasks(
        self,
        project_key: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ProjectTask]:
        """タスク一覧を取得"""
        jql = f"project = {project_key}"
        if status:
            jql += f" AND status = '{status}'"
        jql += " ORDER BY created DESC"

        response = await self.client.get(
            "/search",
            params={
                "jql": jql,
                "maxResults": limit,
                "fields": "summary,description,status,priority,assignee,duedate",
            },
        )
        response.raise_for_status()
        data = response.json()

        tasks = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            tasks.append(
                ProjectTask(
                    id=issue["key"],
                    title=fields["summary"],
                    description=fields.get("description"),
                    status=fields["status"]["name"],
                    priority=fields.get("priority", {}).get("name") if fields.get("priority") else None,
                    assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                    due_date=datetime.fromisoformat(fields["duedate"]) if fields.get("duedate") else None,
                    project_id=project_key,
                    provider="jira",
                )
            )

        return tasks

    async def create_task(
        self,
        project_key: str,
        title: str,
        description: Optional[str] = None,
        issue_type: str = "Task",
        priority: Optional[str] = None,
        assignee_id: Optional[str] = None,
        due_date: Optional[datetime] = None,
    ) -> ProjectTask:
        """タスクを作成"""
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": title,
                "issuetype": {"name": issue_type},
            }
        }

        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        if priority:
            payload["fields"]["priority"] = {"name": priority}
        if assignee_id:
            payload["fields"]["assignee"] = {"id": assignee_id}
        if due_date:
            payload["fields"]["duedate"] = due_date.strftime("%Y-%m-%d")

        response = await self.client.post("/issue", json=payload)
        response.raise_for_status()
        data = response.json()

        return ProjectTask(
            id=data["key"],
            title=title,
            description=description,
            status="To Do",
            priority=priority,
            assignee=None,
            due_date=due_date,
            project_id=project_key,
            provider="jira",
        )

    async def create_tasks_from_action_items(
        self,
        project_key: str,
        action_items: List[dict],
    ) -> List[ProjectTask]:
        """アクションアイテムからタスクを作成"""
        tasks = []
        for item in action_items:
            task = await self.create_task(
                project_key=project_key,
                title=item.get("title", item.get("text", "アクションアイテム")),
                description=item.get("description"),
                priority=item.get("priority", "Medium"),
                due_date=datetime.fromisoformat(item["due_date"]) if item.get("due_date") else None,
            )
            tasks.append(task)

        return tasks

    async def close(self):
        await self.client.aclose()


class AsanaService:
    """Asana連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url="https://app.asana.com/api/1.0",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get_workspaces(self) -> List[dict]:
        """ワークスペース一覧を取得"""
        response = await self.client.get("/workspaces")
        response.raise_for_status()
        return response.json().get("data", [])

    async def get_projects(self, workspace_gid: str) -> List[Project]:
        """プロジェクト一覧を取得"""
        response = await self.client.get(
            "/projects",
            params={"workspace": workspace_gid},
        )
        response.raise_for_status()
        data = response.json()

        projects = []
        for p in data.get("data", []):
            projects.append(
                Project(
                    id=p["gid"],
                    name=p["name"],
                    description=None,
                    status=None,
                    provider="asana",
                )
            )

        return projects

    async def get_tasks(
        self,
        project_gid: str,
        completed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[ProjectTask]:
        """タスク一覧を取得"""
        params = {
            "project": project_gid,
            "limit": limit,
            "opt_fields": "name,notes,completed,assignee.name,due_on",
        }

        if completed is not None:
            params["completed"] = str(completed).lower()

        response = await self.client.get("/tasks", params=params)
        response.raise_for_status()
        data = response.json()

        tasks = []
        for t in data.get("data", []):
            tasks.append(
                ProjectTask(
                    id=t["gid"],
                    title=t["name"],
                    description=t.get("notes"),
                    status="completed" if t.get("completed") else "pending",
                    priority=None,
                    assignee=t.get("assignee", {}).get("name") if t.get("assignee") else None,
                    due_date=datetime.fromisoformat(t["due_on"]) if t.get("due_on") else None,
                    project_id=project_gid,
                    provider="asana",
                )
            )

        return tasks

    async def create_task(
        self,
        project_gid: str,
        title: str,
        description: Optional[str] = None,
        assignee_gid: Optional[str] = None,
        due_date: Optional[datetime] = None,
    ) -> ProjectTask:
        """タスクを作成"""
        payload = {
            "data": {
                "name": title,
                "projects": [project_gid],
            }
        }

        if description:
            payload["data"]["notes"] = description
        if assignee_gid:
            payload["data"]["assignee"] = assignee_gid
        if due_date:
            payload["data"]["due_on"] = due_date.strftime("%Y-%m-%d")

        response = await self.client.post("/tasks", json=payload)
        response.raise_for_status()
        data = response.json()

        return ProjectTask(
            id=data["data"]["gid"],
            title=title,
            description=description,
            status="pending",
            priority=None,
            assignee=None,
            due_date=due_date,
            project_id=project_gid,
            provider="asana",
        )

    async def create_tasks_from_action_items(
        self,
        project_gid: str,
        action_items: List[dict],
    ) -> List[ProjectTask]:
        """アクションアイテムからタスクを作成"""
        tasks = []
        for item in action_items:
            task = await self.create_task(
                project_gid=project_gid,
                title=item.get("title", item.get("text", "アクションアイテム")),
                description=item.get("description"),
                due_date=datetime.fromisoformat(item["due_date"]) if item.get("due_date") else None,
            )
            tasks.append(task)

        return tasks

    async def close(self):
        await self.client.aclose()


class NotionService:
    """Notion連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            },
            timeout=30.0,
        )

    async def get_databases(self) -> List[Project]:
        """データベース一覧を取得"""
        response = await self.client.post(
            "/search",
            json={
                "filter": {"property": "object", "value": "database"},
            },
        )
        response.raise_for_status()
        data = response.json()

        databases = []
        for db in data.get("results", []):
            title = ""
            if db.get("title"):
                title = "".join([t.get("plain_text", "") for t in db["title"]])

            databases.append(
                Project(
                    id=db["id"],
                    name=title or "Untitled",
                    description=None,
                    status=None,
                    provider="notion",
                )
            )

        return databases

    async def get_pages(
        self,
        database_id: str,
        limit: int = 50,
    ) -> List[ProjectTask]:
        """ページ一覧を取得"""
        response = await self.client.post(
            f"/databases/{database_id}/query",
            json={"page_size": limit},
        )
        response.raise_for_status()
        data = response.json()

        tasks = []
        for page in data.get("results", []):
            props = page.get("properties", {})

            # タイトルを取得
            title = ""
            for prop in props.values():
                if prop.get("type") == "title":
                    title = "".join([t.get("plain_text", "") for t in prop.get("title", [])])
                    break

            # ステータスを取得
            status = "pending"
            if "Status" in props:
                status_prop = props["Status"]
                if status_prop.get("status"):
                    status = status_prop["status"].get("name", "pending")
                elif status_prop.get("select"):
                    status = status_prop["select"].get("name", "pending")

            tasks.append(
                ProjectTask(
                    id=page["id"],
                    title=title or "Untitled",
                    description=None,
                    status=status,
                    priority=None,
                    assignee=None,
                    due_date=None,
                    project_id=database_id,
                    provider="notion",
                )
            )

        return tasks

    async def create_page(
        self,
        database_id: str,
        title: str,
        properties: Optional[dict] = None,
        content: Optional[str] = None,
    ) -> ProjectTask:
        """ページを作成"""
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": title}}]
                }
            },
        }

        if properties:
            payload["properties"].update(properties)

        if content:
            payload["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]

        response = await self.client.post("/pages", json=payload)
        response.raise_for_status()
        data = response.json()

        return ProjectTask(
            id=data["id"],
            title=title,
            description=content,
            status="pending",
            priority=None,
            assignee=None,
            due_date=None,
            project_id=database_id,
            provider="notion",
        )

    async def create_meeting_notes_page(
        self,
        database_id: str,
        title: str,
        summary: str,
        action_items: List[dict],
        participants: List[str],
    ) -> str:
        """会議議事録ページを作成"""
        # 参加者リスト
        participants_text = ", ".join(participants) if participants else "なし"

        # アクションアイテム
        action_blocks = []
        for item in action_items:
            action_blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": item.get("text", item.get("title", ""))}}],
                    "checked": False,
                },
            })

        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": f"会議議事録: {title}"}}]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "参加者"}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": participants_text}}]
                    },
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "概要"}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary}}]
                    },
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "アクションアイテム"}}]
                    },
                },
                *action_blocks,
            ],
        }

        response = await self.client.post("/pages", json=payload)
        response.raise_for_status()
        data = response.json()

        return data["id"]

    async def close(self):
        await self.client.aclose()


class ProjectManagementService:
    """プロジェクト管理統合サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_service(
        self,
        provider: str,
        credentials: dict,
    ):
        """プロバイダーに応じたサービスを取得"""
        if provider == "jira":
            return JiraService(
                email=credentials["email"],
                api_token=credentials["api_token"],
                domain=credentials["domain"],
            )
        elif provider == "asana":
            return AsanaService(access_token=credentials["access_token"])
        elif provider == "notion":
            return NotionService(access_token=credentials["access_token"])
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def export_action_items(
        self,
        provider: str,
        credentials: dict,
        project_id: str,
        action_items: List[dict],
    ) -> List[ProjectTask]:
        """アクションアイテムをタスクとしてエクスポート"""
        service = self.get_service(provider, credentials)

        try:
            if provider == "jira":
                return await service.create_tasks_from_action_items(
                    project_key=project_id,
                    action_items=action_items,
                )
            elif provider == "asana":
                return await service.create_tasks_from_action_items(
                    project_gid=project_id,
                    action_items=action_items,
                )
            elif provider == "notion":
                tasks = []
                for item in action_items:
                    task = await service.create_page(
                        database_id=project_id,
                        title=item.get("title", item.get("text", "アクションアイテム")),
                        content=item.get("description"),
                    )
                    tasks.append(task)
                return tasks
        finally:
            await service.close()

    async def export_meeting_notes(
        self,
        provider: str,
        credentials: dict,
        project_id: str,
        title: str,
        summary: str,
        action_items: List[dict],
        participants: List[str],
    ) -> str:
        """会議議事録をエクスポート"""
        service = self.get_service(provider, credentials)

        try:
            if provider == "notion":
                return await service.create_meeting_notes_page(
                    database_id=project_id,
                    title=title,
                    summary=summary,
                    action_items=action_items,
                    participants=participants,
                )
            else:
                # Jira/Asanaの場合は説明付きタスクとして作成
                description = f"""
会議: {title}
参加者: {', '.join(participants)}

概要:
{summary}

アクションアイテム:
""" + "\n".join([f"- {item.get('text', item.get('title', ''))}" for item in action_items])

                if provider == "jira":
                    task = await service.create_task(
                        project_key=project_id,
                        title=f"会議議事録: {title}",
                        description=description,
                        issue_type="Task",
                    )
                    return task.id
                else:  # asana
                    task = await service.create_task(
                        project_gid=project_id,
                        title=f"会議議事録: {title}",
                        description=description,
                    )
                    return task.id
        finally:
            await service.close()
