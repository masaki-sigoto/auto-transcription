"""ワークフロー自動化・インテグレーションサービス"""

import asyncio
import uuid
import json
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from abc import ABC, abstractmethod
import httpx


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TriggerType(str, Enum):
    TRANSCRIPTION_CREATED = "transcription.created"
    TRANSCRIPTION_COMPLETED = "transcription.completed"
    ANALYSIS_COMPLETED = "analysis.completed"
    KEYWORD_DETECTED = "keyword.detected"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK_RECEIVED = "webhook.received"


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_SLACK = "send_slack"
    SEND_TEAMS = "send_teams"
    SEND_WEBHOOK = "send_webhook"
    GENERATE_SUMMARY = "generate_summary"
    GENERATE_MINUTES = "generate_minutes"
    EXPORT_FILE = "export_file"
    NOTIFY_USER = "notify_user"
    RUN_CUSTOM_SCRIPT = "run_custom_script"
    CREATE_TASK = "create_task"
    UPDATE_CRM = "update_crm"
    SAVE_TO_STORAGE = "save_to_storage"


class ConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    REGEX = "regex"
    EXISTS = "exists"


@dataclass
class WorkflowCondition:
    field: str
    operator: ConditionOperator
    value: Any

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """条件を評価"""
        field_value = self._get_nested_value(context, self.field)

        if self.operator == ConditionOperator.EQUALS:
            return field_value == self.value
        elif self.operator == ConditionOperator.NOT_EQUALS:
            return field_value != self.value
        elif self.operator == ConditionOperator.CONTAINS:
            return self.value in str(field_value) if field_value else False
        elif self.operator == ConditionOperator.NOT_CONTAINS:
            return self.value not in str(field_value) if field_value else True
        elif self.operator == ConditionOperator.GREATER_THAN:
            return float(field_value) > float(self.value) if field_value else False
        elif self.operator == ConditionOperator.LESS_THAN:
            return float(field_value) < float(self.value) if field_value else False
        elif self.operator == ConditionOperator.REGEX:
            import re
            return bool(re.search(self.value, str(field_value))) if field_value else False
        elif self.operator == ConditionOperator.EXISTS:
            return field_value is not None

        return False

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """ネストされた値を取得"""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


@dataclass
class WorkflowAction:
    action_type: ActionType
    config: Dict[str, Any] = field(default_factory=dict)
    conditions: List[WorkflowCondition] = field(default_factory=list)


@dataclass
class WorkflowTrigger:
    trigger_type: TriggerType
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Workflow:
    id: str
    name: str
    description: str
    user_id: str
    trigger: WorkflowTrigger
    actions: List[WorkflowAction]
    status: WorkflowStatus = WorkflowStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    run_count: int = 0
    last_run_at: Optional[datetime] = None


@dataclass
class WorkflowExecution:
    id: str
    workflow_id: str
    status: str  # running, completed, failed
    trigger_data: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class BaseActionExecutor(ABC):
    """アクション実行の基底クラス"""

    @abstractmethod
    async def execute(
        self,
        action: WorkflowAction,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        pass


class EmailActionExecutor(BaseActionExecutor):
    """メール送信アクション"""

    async def execute(
        self,
        action: WorkflowAction,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        config = action.config
        to_email = config.get("to", "")
        subject = self._render_template(config.get("subject", ""), context)
        body = self._render_template(config.get("body", ""), context)

        # 実際の実装ではメール送信サービスを使用
        return {
            "action": "send_email",
            "to": to_email,
            "subject": subject,
            "status": "sent",
        }

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """テンプレートをレンダリング"""
        for key, value in context.items():
            if isinstance(value, str):
                template = template.replace(f"{{{{{key}}}}}", value)
        return template


class SlackActionExecutor(BaseActionExecutor):
    """Slack送信アクション"""

    async def execute(
        self,
        action: WorkflowAction,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        config = action.config
        webhook_url = config.get("webhook_url", "")
        channel = config.get("channel", "")
        message = self._render_template(config.get("message", ""), context)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    webhook_url,
                    json={
                        "channel": channel,
                        "text": message,
                        "username": config.get("username", "Transcription Bot"),
                    },
                    timeout=10,
                )
                return {
                    "action": "send_slack",
                    "channel": channel,
                    "status": "sent" if response.status_code == 200 else "failed",
                }
            except Exception as e:
                return {
                    "action": "send_slack",
                    "status": "failed",
                    "error": str(e),
                }

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        for key, value in context.items():
            if isinstance(value, str):
                template = template.replace(f"{{{{{key}}}}}", value)
        return template


class TeamsActionExecutor(BaseActionExecutor):
    """Microsoft Teams送信アクション"""

    async def execute(
        self,
        action: WorkflowAction,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        config = action.config
        webhook_url = config.get("webhook_url", "")
        title = self._render_template(config.get("title", ""), context)
        message = self._render_template(config.get("message", ""), context)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    webhook_url,
                    json={
                        "@type": "MessageCard",
                        "@context": "http://schema.org/extensions",
                        "summary": title,
                        "title": title,
                        "text": message,
                    },
                    timeout=10,
                )
                return {
                    "action": "send_teams",
                    "status": "sent" if response.status_code == 200 else "failed",
                }
            except Exception as e:
                return {
                    "action": "send_teams",
                    "status": "failed",
                    "error": str(e),
                }

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        for key, value in context.items():
            if isinstance(value, str):
                template = template.replace(f"{{{{{key}}}}}", value)
        return template


class WebhookActionExecutor(BaseActionExecutor):
    """Webhook送信アクション"""

    async def execute(
        self,
        action: WorkflowAction,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        config = action.config
        url = config.get("url", "")
        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=context,
                    headers=headers,
                    timeout=30,
                )
                return {
                    "action": "send_webhook",
                    "url": url,
                    "status_code": response.status_code,
                    "status": "sent" if response.status_code < 400 else "failed",
                }
            except Exception as e:
                return {
                    "action": "send_webhook",
                    "status": "failed",
                    "error": str(e),
                }


class WorkflowEngine:
    """ワークフローエンジン"""

    def __init__(self):
        self.executors: Dict[ActionType, BaseActionExecutor] = {
            ActionType.SEND_EMAIL: EmailActionExecutor(),
            ActionType.SEND_SLACK: SlackActionExecutor(),
            ActionType.SEND_TEAMS: TeamsActionExecutor(),
            ActionType.SEND_WEBHOOK: WebhookActionExecutor(),
        }

    async def execute_workflow(
        self,
        workflow: Workflow,
        trigger_data: Dict[str, Any],
    ) -> WorkflowExecution:
        """ワークフローを実行"""
        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            status="running",
            trigger_data=trigger_data,
            started_at=datetime.utcnow(),
        )

        context = {
            "trigger": trigger_data,
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            for action in workflow.actions:
                # 条件チェック
                if action.conditions:
                    all_conditions_met = all(
                        cond.evaluate(context) for cond in action.conditions
                    )
                    if not all_conditions_met:
                        execution.results.append({
                            "action": action.action_type.value,
                            "status": "skipped",
                            "reason": "conditions not met",
                        })
                        continue

                # アクション実行
                executor = self.executors.get(action.action_type)
                if executor:
                    result = await executor.execute(action, context)
                    execution.results.append(result)
                else:
                    execution.results.append({
                        "action": action.action_type.value,
                        "status": "skipped",
                        "reason": "no executor found",
                    })

            execution.status = "completed"

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)

        execution.completed_at = datetime.utcnow()
        return execution


class WorkflowService:
    """ワークフローサービス"""

    def __init__(self, db=None):
        self.db = db
        self.engine = WorkflowEngine()
        self._workflows: Dict[str, Workflow] = {}  # インメモリストア（実際はDB）

    async def create_workflow(
        self,
        user_id: uuid.UUID,
        name: str,
        description: str,
        trigger: Dict[str, Any],
        actions: List[Dict[str, Any]],
    ) -> Workflow:
        """ワークフローを作成"""
        workflow_id = str(uuid.uuid4())

        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description,
            user_id=str(user_id),
            trigger=WorkflowTrigger(
                trigger_type=TriggerType(trigger["type"]),
                config=trigger.get("config", {}),
            ),
            actions=[
                WorkflowAction(
                    action_type=ActionType(a["type"]),
                    config=a.get("config", {}),
                    conditions=[
                        WorkflowCondition(
                            field=c["field"],
                            operator=ConditionOperator(c["operator"]),
                            value=c["value"],
                        )
                        for c in a.get("conditions", [])
                    ],
                )
                for a in actions
            ],
            status=WorkflowStatus.DRAFT,
        )

        self._workflows[workflow_id] = workflow
        return workflow

    async def get_workflow(
        self,
        workflow_id: str,
        user_id: uuid.UUID,
    ) -> Optional[Workflow]:
        """ワークフローを取得"""
        workflow = self._workflows.get(workflow_id)
        if workflow and workflow.user_id == str(user_id):
            return workflow
        return None

    async def list_workflows(
        self,
        user_id: uuid.UUID,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]:
        """ワークフロー一覧を取得"""
        workflows = [
            w for w in self._workflows.values()
            if w.user_id == str(user_id)
        ]

        if status:
            workflows = [w for w in workflows if w.status == status]

        return workflows

    async def update_workflow(
        self,
        workflow_id: str,
        user_id: uuid.UUID,
        updates: Dict[str, Any],
    ) -> Optional[Workflow]:
        """ワークフローを更新"""
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return None

        if "name" in updates:
            workflow.name = updates["name"]
        if "description" in updates:
            workflow.description = updates["description"]
        if "status" in updates:
            workflow.status = WorkflowStatus(updates["status"])

        workflow.updated_at = datetime.utcnow()
        return workflow

    async def delete_workflow(
        self,
        workflow_id: str,
        user_id: uuid.UUID,
    ) -> bool:
        """ワークフローを削除"""
        workflow = await self.get_workflow(workflow_id, user_id)
        if workflow:
            del self._workflows[workflow_id]
            return True
        return False

    async def trigger_workflow(
        self,
        workflow_id: str,
        trigger_data: Dict[str, Any],
    ) -> Optional[WorkflowExecution]:
        """ワークフローをトリガー"""
        workflow = self._workflows.get(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return None

        execution = await self.engine.execute_workflow(workflow, trigger_data)

        # 統計更新
        workflow.run_count += 1
        workflow.last_run_at = datetime.utcnow()

        return execution

    async def trigger_by_event(
        self,
        event_type: TriggerType,
        event_data: Dict[str, Any],
    ) -> List[WorkflowExecution]:
        """イベントによるワークフロートリガー"""
        executions = []

        for workflow in self._workflows.values():
            if (
                workflow.status == WorkflowStatus.ACTIVE
                and workflow.trigger.trigger_type == event_type
            ):
                execution = await self.trigger_workflow(workflow.id, event_data)
                if execution:
                    executions.append(execution)

        return executions


class IntegrationService:
    """外部サービス統合"""

    def __init__(self):
        self.integrations: Dict[str, Dict[str, Any]] = {}

    async def connect_slack(
        self,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Slack連携"""
        # 実際の実装ではOAuth2フローを実行
        integration_id = str(uuid.uuid4())

        self.integrations[integration_id] = {
            "type": "slack",
            "user_id": str(user_id),
            "connected_at": datetime.utcnow().isoformat(),
            "status": "connected",
        }

        return {
            "integration_id": integration_id,
            "type": "slack",
            "status": "connected",
        }

    async def connect_teams(
        self,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Microsoft Teams連携"""
        integration_id = str(uuid.uuid4())

        self.integrations[integration_id] = {
            "type": "teams",
            "user_id": str(user_id),
            "connected_at": datetime.utcnow().isoformat(),
            "status": "connected",
        }

        return {
            "integration_id": integration_id,
            "type": "teams",
            "status": "connected",
        }

    async def connect_google_drive(
        self,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Google Drive連携"""
        integration_id = str(uuid.uuid4())

        self.integrations[integration_id] = {
            "type": "google_drive",
            "user_id": str(user_id),
            "connected_at": datetime.utcnow().isoformat(),
            "status": "connected",
        }

        return {
            "integration_id": integration_id,
            "type": "google_drive",
            "status": "connected",
        }

    async def connect_notion(
        self,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Notion連携"""
        integration_id = str(uuid.uuid4())

        self.integrations[integration_id] = {
            "type": "notion",
            "user_id": str(user_id),
            "connected_at": datetime.utcnow().isoformat(),
            "status": "connected",
        }

        return {
            "integration_id": integration_id,
            "type": "notion",
            "status": "connected",
        }

    async def connect_salesforce(
        self,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Salesforce連携"""
        integration_id = str(uuid.uuid4())

        self.integrations[integration_id] = {
            "type": "salesforce",
            "user_id": str(user_id),
            "connected_at": datetime.utcnow().isoformat(),
            "status": "connected",
        }

        return {
            "integration_id": integration_id,
            "type": "salesforce",
            "status": "connected",
        }

    async def list_integrations(
        self,
        user_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """連携一覧を取得"""
        return [
            {**integration, "id": integration_id}
            for integration_id, integration in self.integrations.items()
            if integration["user_id"] == str(user_id)
        ]

    async def disconnect(
        self,
        integration_id: str,
        user_id: uuid.UUID,
    ) -> bool:
        """連携を解除"""
        integration = self.integrations.get(integration_id)
        if integration and integration["user_id"] == str(user_id):
            del self.integrations[integration_id]
            return True
        return False
