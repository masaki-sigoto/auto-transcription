"""ワークフロー自動化APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.workflow_service import (
    WorkflowService,
    IntegrationService,
    WorkflowStatus,
    TriggerType,
    ActionType,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === ワークフロー CRUD ===

class WorkflowConditionInput(BaseModel):
    field: str
    operator: str
    value: str


class WorkflowActionInput(BaseModel):
    type: str
    config: dict = {}
    conditions: List[WorkflowConditionInput] = []


class WorkflowTriggerInput(BaseModel):
    type: str
    config: dict = {}


class WorkflowCreateRequest(BaseModel):
    name: str
    description: str = ""
    trigger: WorkflowTriggerInput
    actions: List[WorkflowActionInput]


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    trigger_type: str
    action_count: int
    run_count: int
    created_at: str
    last_run_at: Optional[str] = None


@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowCreateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを作成"""
    service = WorkflowService()

    workflow = await service.create_workflow(
        user_id=user_id,
        name=request.name,
        description=request.description,
        trigger={
            "type": request.trigger.type,
            "config": request.trigger.config,
        },
        actions=[
            {
                "type": action.type,
                "config": action.config,
                "conditions": [
                    {
                        "field": c.field,
                        "operator": c.operator,
                        "value": c.value,
                    }
                    for c in action.conditions
                ],
            }
            for action in request.actions
        ],
    )

    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=workflow.status.value,
        trigger_type=workflow.trigger.trigger_type.value,
        action_count=len(workflow.actions),
        run_count=workflow.run_count,
        created_at=workflow.created_at.isoformat(),
    )


@router.get("", response_model=List[WorkflowResponse])
async def list_workflows(
    status: Optional[str] = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフロー一覧を取得"""
    service = WorkflowService()

    workflow_status = None
    if status:
        try:
            workflow_status = WorkflowStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")

    workflows = await service.list_workflows(user_id, workflow_status)

    return [
        WorkflowResponse(
            id=w.id,
            name=w.name,
            description=w.description,
            status=w.status.value,
            trigger_type=w.trigger.trigger_type.value,
            action_count=len(w.actions),
            run_count=w.run_count,
            created_at=w.created_at.isoformat(),
            last_run_at=w.last_run_at.isoformat() if w.last_run_at else None,
        )
        for w in workflows
    ]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを取得"""
    service = WorkflowService()

    workflow = await service.get_workflow(workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=workflow.status.value,
        trigger_type=workflow.trigger.trigger_type.value,
        action_count=len(workflow.actions),
        run_count=workflow.run_count,
        created_at=workflow.created_at.isoformat(),
        last_run_at=workflow.last_run_at.isoformat() if workflow.last_run_at else None,
    )


class WorkflowUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを更新"""
    service = WorkflowService()

    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.status is not None:
        updates["status"] = request.status

    workflow = await service.update_workflow(workflow_id, user_id, updates)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=workflow.status.value,
        trigger_type=workflow.trigger.trigger_type.value,
        action_count=len(workflow.actions),
        run_count=workflow.run_count,
        created_at=workflow.created_at.isoformat(),
        last_run_at=workflow.last_run_at.isoformat() if workflow.last_run_at else None,
    )


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを削除"""
    service = WorkflowService()

    deleted = await service.delete_workflow(workflow_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {"status": "deleted", "workflow_id": workflow_id}


# === ワークフロー実行 ===

class WorkflowTriggerRequest(BaseModel):
    data: dict = {}


@router.post("/{workflow_id}/trigger")
async def trigger_workflow(
    workflow_id: str,
    request: WorkflowTriggerRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを手動トリガー"""
    service = WorkflowService()

    execution = await service.trigger_workflow(workflow_id, request.data)
    if not execution:
        raise HTTPException(
            status_code=400,
            detail="Workflow not found or not active"
        )

    return {
        "execution_id": execution.id,
        "workflow_id": execution.workflow_id,
        "status": execution.status,
        "started_at": execution.started_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "results": execution.results,
        "error": execution.error,
    }


@router.post("/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを有効化"""
    service = WorkflowService()

    workflow = await service.update_workflow(
        workflow_id,
        user_id,
        {"status": "active"},
    )

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {"status": "activated", "workflow_id": workflow_id}


@router.post("/{workflow_id}/pause")
async def pause_workflow(
    workflow_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワークフローを一時停止"""
    service = WorkflowService()

    workflow = await service.update_workflow(
        workflow_id,
        user_id,
        {"status": "paused"},
    )

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {"status": "paused", "workflow_id": workflow_id}


# === トリガー・アクションタイプ ===

@router.get("/meta/triggers")
async def list_trigger_types():
    """利用可能なトリガータイプ一覧"""
    return {
        "triggers": [
            {
                "type": TriggerType.TRANSCRIPTION_CREATED.value,
                "name": "文字起こし作成時",
                "description": "新しい文字起こしが作成されたとき",
            },
            {
                "type": TriggerType.TRANSCRIPTION_COMPLETED.value,
                "name": "文字起こし完了時",
                "description": "文字起こしが完了したとき",
            },
            {
                "type": TriggerType.ANALYSIS_COMPLETED.value,
                "name": "分析完了時",
                "description": "AI分析が完了したとき",
            },
            {
                "type": TriggerType.KEYWORD_DETECTED.value,
                "name": "キーワード検出時",
                "description": "特定のキーワードが検出されたとき",
            },
            {
                "type": TriggerType.SCHEDULED.value,
                "name": "スケジュール",
                "description": "定期的なスケジュール実行",
            },
            {
                "type": TriggerType.MANUAL.value,
                "name": "手動",
                "description": "手動でトリガー",
            },
            {
                "type": TriggerType.WEBHOOK_RECEIVED.value,
                "name": "Webhook受信時",
                "description": "外部からのWebhook受信時",
            },
        ]
    }


@router.get("/meta/actions")
async def list_action_types():
    """利用可能なアクションタイプ一覧"""
    return {
        "actions": [
            {
                "type": ActionType.SEND_EMAIL.value,
                "name": "メール送信",
                "description": "メールを送信",
                "config_schema": {
                    "to": "string",
                    "subject": "string",
                    "body": "string",
                },
            },
            {
                "type": ActionType.SEND_SLACK.value,
                "name": "Slack通知",
                "description": "Slackにメッセージを送信",
                "config_schema": {
                    "webhook_url": "string",
                    "channel": "string",
                    "message": "string",
                },
            },
            {
                "type": ActionType.SEND_TEAMS.value,
                "name": "Teams通知",
                "description": "Microsoft Teamsにメッセージを送信",
                "config_schema": {
                    "webhook_url": "string",
                    "title": "string",
                    "message": "string",
                },
            },
            {
                "type": ActionType.SEND_WEBHOOK.value,
                "name": "Webhook送信",
                "description": "外部Webhookにデータを送信",
                "config_schema": {
                    "url": "string",
                    "method": "string",
                    "headers": "object",
                },
            },
            {
                "type": ActionType.GENERATE_SUMMARY.value,
                "name": "要約生成",
                "description": "AI要約を生成",
            },
            {
                "type": ActionType.GENERATE_MINUTES.value,
                "name": "議事録生成",
                "description": "AI議事録を生成",
            },
            {
                "type": ActionType.EXPORT_FILE.value,
                "name": "ファイルエクスポート",
                "description": "ファイル形式でエクスポート",
                "config_schema": {
                    "format": "string",
                    "destination": "string",
                },
            },
            {
                "type": ActionType.NOTIFY_USER.value,
                "name": "ユーザー通知",
                "description": "アプリ内通知を送信",
            },
        ]
    }


# === インテグレーション ===

integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])


@integrations_router.get("")
async def list_integrations(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """連携一覧を取得"""
    service = IntegrationService()
    integrations = await service.list_integrations(user_id)

    return {"integrations": integrations}


@integrations_router.get("/available")
async def list_available_integrations():
    """利用可能な連携サービス一覧"""
    return {
        "available": [
            {
                "type": "slack",
                "name": "Slack",
                "description": "Slackワークスペースと連携",
                "oauth_url": "/integrations/slack/connect",
            },
            {
                "type": "teams",
                "name": "Microsoft Teams",
                "description": "Microsoft Teamsと連携",
                "oauth_url": "/integrations/teams/connect",
            },
            {
                "type": "google_drive",
                "name": "Google Drive",
                "description": "Google Driveと連携してファイルを保存",
                "oauth_url": "/integrations/google-drive/connect",
            },
            {
                "type": "notion",
                "name": "Notion",
                "description": "Notionにドキュメントを保存",
                "oauth_url": "/integrations/notion/connect",
            },
            {
                "type": "salesforce",
                "name": "Salesforce",
                "description": "SalesforceにCRMデータを連携",
                "oauth_url": "/integrations/salesforce/connect",
            },
        ]
    }


class ConnectRequest(BaseModel):
    oauth_code: str


@integrations_router.post("/slack/connect")
async def connect_slack(
    request: ConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Slack連携"""
    service = IntegrationService()
    result = await service.connect_slack(user_id, request.oauth_code)
    return result


@integrations_router.post("/teams/connect")
async def connect_teams(
    request: ConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Microsoft Teams連携"""
    service = IntegrationService()
    result = await service.connect_teams(user_id, request.oauth_code)
    return result


@integrations_router.post("/google-drive/connect")
async def connect_google_drive(
    request: ConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Google Drive連携"""
    service = IntegrationService()
    result = await service.connect_google_drive(user_id, request.oauth_code)
    return result


@integrations_router.post("/notion/connect")
async def connect_notion(
    request: ConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Notion連携"""
    service = IntegrationService()
    result = await service.connect_notion(user_id, request.oauth_code)
    return result


@integrations_router.post("/salesforce/connect")
async def connect_salesforce(
    request: ConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Salesforce連携"""
    service = IntegrationService()
    result = await service.connect_salesforce(user_id, request.oauth_code)
    return result


@integrations_router.delete("/{integration_id}")
async def disconnect_integration(
    integration_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """連携を解除"""
    service = IntegrationService()
    disconnected = await service.disconnect(integration_id, user_id)

    if not disconnected:
        raise HTTPException(status_code=404, detail="Integration not found")

    return {"status": "disconnected", "integration_id": integration_id}


# ルーターをマージ
router.include_router(integrations_router)
