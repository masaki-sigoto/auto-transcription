"""Zapier/Make/n8n自動化連携APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel

from app.services.automation_service import (
    webhook_manager,
    api_key_manager,
    workflow_templates,
    custom_workflow_engine,
    automation_platform_manager,
    TriggerEvent,
)

router = APIRouter(prefix="/automation", tags=["automation"])


async def get_current_tenant_id() -> str:
    return "default-tenant"


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """APIキー認証"""
    if not x_api_key:
        return None
    return await api_key_manager.validate_api_key(x_api_key)


# =====================
# Webhook管理
# =====================

class CreateWebhookRequest(BaseModel):
    url: str
    events: List[str]


@router.post("/webhooks")
async def create_webhook(
    request: CreateWebhookRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Webhookを作成"""
    # イベント名を検証
    try:
        for event in request.events:
            TriggerEvent(event)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid event: {e}")

    subscription = await webhook_manager.create_subscription(
        tenant_id=tenant_id,
        url=request.url,
        events=request.events,
    )

    return {
        "id": subscription.id,
        "url": subscription.url,
        "events": [e.value for e in subscription.events],
        "secret": subscription.secret,
        "active": subscription.active,
        "created_at": subscription.created_at.isoformat(),
    }


@router.get("/webhooks")
async def list_webhooks(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Webhook一覧"""
    subscriptions = await webhook_manager.list_subscriptions(tenant_id)

    return {
        "webhooks": [
            {
                "id": s.id,
                "url": s.url,
                "events": [e.value for e in s.events],
                "active": s.active,
                "last_triggered": s.last_triggered.isoformat() if s.last_triggered else None,
                "failure_count": s.failure_count,
                "created_at": s.created_at.isoformat(),
            }
            for s in subscriptions
        ],
        "count": len(subscriptions),
    }


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Webhookを削除"""
    success = await webhook_manager.delete_subscription(webhook_id)

    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"status": "deleted", "webhook_id": webhook_id}


@router.get("/webhooks/{webhook_id}/logs")
async def get_webhook_logs(
    webhook_id: str,
    limit: int = Query(default=50, le=100),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Webhook配信ログ"""
    logs = await webhook_manager.get_delivery_logs(webhook_id, limit)

    return {
        "logs": [
            {
                "id": log.id,
                "event": log.event.value,
                "status_code": log.status_code,
                "success": log.success,
                "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
            }
            for log in logs
        ],
        "count": len(logs),
    }


class TestWebhookRequest(BaseModel):
    event: str
    payload: dict = {}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    request: TestWebhookRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Webhookをテスト"""
    try:
        event = TriggerEvent(request.event)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event: {request.event}")

    deliveries = await webhook_manager.trigger_webhooks(
        tenant_id=tenant_id,
        event=event,
        payload=request.payload,
    )

    return {
        "deliveries": [
            {
                "id": d.id,
                "status_code": d.status_code,
                "success": d.success,
            }
            for d in deliveries
        ],
        "count": len(deliveries),
    }


# =====================
# APIキー管理
# =====================

class CreateAPIKeyRequest(BaseModel):
    name: str
    scopes: List[str] = ["read", "write"]
    expires_in_days: Optional[int] = None


@router.post("/api-keys")
async def create_api_key(
    request: CreateAPIKeyRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """APIキーを作成"""
    expires_at = None
    if request.expires_in_days:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    api_key, raw_key = await api_key_manager.create_api_key(
        tenant_id=tenant_id,
        name=request.name,
        scopes=request.scopes,
        expires_at=expires_at,
    )

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # 一度のみ返される
        "prefix": api_key.prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "warning": "このキーは一度のみ表示されます。安全な場所に保存してください。",
    }


@router.get("/api-keys")
async def list_api_keys(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """APIキー一覧"""
    keys = await api_key_manager.list_api_keys(tenant_id)

    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "prefix": k.prefix,
                "scopes": k.scopes,
                "active": k.active,
                "last_used": k.last_used.isoformat() if k.last_used else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ],
        "count": len(keys),
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """APIキーを無効化"""
    success = await api_key_manager.revoke_api_key(key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"status": "revoked", "key_id": key_id}


# =====================
# ワークフローテンプレート
# =====================

@router.get("/templates")
async def list_workflow_templates(
    platform: Optional[str] = None,
    trigger: Optional[str] = None,
):
    """ワークフローテンプレート一覧"""
    trigger_event = None
    if trigger:
        try:
            trigger_event = TriggerEvent(trigger)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid trigger: {trigger}")

    templates = await workflow_templates.list_templates(platform, trigger_event)

    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "platform": t.platform,
                "trigger": t.trigger.value,
                "actions": t.actions,
                "config_schema": t.config_schema,
            }
            for t in templates
        ],
        "count": len(templates),
    }


@router.get("/templates/{template_id}")
async def get_workflow_template(template_id: str):
    """ワークフローテンプレートを取得"""
    template = await workflow_templates.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "platform": template.platform,
        "trigger": template.trigger.value,
        "actions": template.actions,
        "config_schema": template.config_schema,
    }


# =====================
# カスタムワークフロー
# =====================

class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    trigger: str
    trigger_config: dict = {}
    actions: List[dict]


@router.post("/workflows")
async def create_workflow(
    request: CreateWorkflowRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カスタムワークフローを作成"""
    try:
        TriggerEvent(request.trigger)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trigger: {request.trigger}")

    workflow = await custom_workflow_engine.create_workflow(
        tenant_id=tenant_id,
        name=request.name,
        description=request.description,
        trigger=request.trigger,
        trigger_config=request.trigger_config,
        actions=request.actions,
    )

    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "trigger": workflow.trigger.value,
        "trigger_config": workflow.trigger_config,
        "actions": workflow.actions,
        "active": workflow.active,
        "created_at": workflow.created_at.isoformat(),
    }


@router.get("/workflows")
async def list_workflows(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カスタムワークフロー一覧"""
    workflows = await custom_workflow_engine.list_workflows(tenant_id)

    return {
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "trigger": w.trigger.value,
                "active": w.active,
                "execution_count": w.execution_count,
                "last_executed": w.last_executed.isoformat() if w.last_executed else None,
                "created_at": w.created_at.isoformat(),
            }
            for w in workflows
        ],
        "count": len(workflows),
    }


class UpdateWorkflowRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_config: Optional[dict] = None
    actions: Optional[List[dict]] = None
    active: Optional[bool] = None


@router.patch("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    request: UpdateWorkflowRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ワークフローを更新"""
    workflow = await custom_workflow_engine.update_workflow(
        workflow_id=workflow_id,
        name=request.name,
        description=request.description,
        trigger_config=request.trigger_config,
        actions=request.actions,
        active=request.active,
    )

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "trigger": workflow.trigger.value,
        "trigger_config": workflow.trigger_config,
        "actions": workflow.actions,
        "active": workflow.active,
        "updated_at": workflow.updated_at.isoformat(),
    }


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ワークフローを削除"""
    success = await custom_workflow_engine.delete_workflow(workflow_id)

    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {"status": "deleted", "workflow_id": workflow_id}


class ExecuteWorkflowRequest(BaseModel):
    event: str
    data: dict


@router.post("/workflows/execute")
async def execute_workflows(
    request: ExecuteWorkflowRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ワークフローを手動実行"""
    try:
        event = TriggerEvent(request.event)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event: {request.event}")

    results = await custom_workflow_engine.execute_workflows(
        tenant_id=tenant_id,
        event=event,
        data=request.data,
    )

    return {
        "results": results,
        "count": len(results),
        "success_count": sum(1 for r in results if r.get("success")),
    }


# =====================
# プラットフォーム連携
# =====================

class SetupZapierRequest(BaseModel):
    zap_id: str
    trigger_url: str


@router.post("/platforms/zapier")
async def setup_zapier(
    request: SetupZapierRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Zapier連携をセットアップ"""
    integration = await automation_platform_manager.setup_zapier(
        tenant_id=tenant_id,
        zap_id=request.zap_id,
        trigger_url=request.trigger_url,
    )

    return {
        "id": integration.id,
        "platform": "zapier",
        "zap_id": integration.zap_id,
        "trigger_url": integration.trigger_url,
        "active": integration.active,
        "created_at": integration.created_at.isoformat(),
    }


class SetupMakeRequest(BaseModel):
    scenario_id: str
    webhook_url: str


@router.post("/platforms/make")
async def setup_make(
    request: SetupMakeRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Make連携をセットアップ"""
    integration = await automation_platform_manager.setup_make(
        tenant_id=tenant_id,
        scenario_id=request.scenario_id,
        webhook_url=request.webhook_url,
    )

    return {
        "id": integration.id,
        "platform": "make",
        "scenario_id": integration.scenario_id,
        "webhook_url": integration.webhook_url,
        "active": integration.active,
        "created_at": integration.created_at.isoformat(),
    }


class SetupN8nRequest(BaseModel):
    workflow_id: str
    webhook_url: str


@router.post("/platforms/n8n")
async def setup_n8n(
    request: SetupN8nRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """n8n連携をセットアップ"""
    integration = await automation_platform_manager.setup_n8n(
        tenant_id=tenant_id,
        workflow_id=request.workflow_id,
        webhook_url=request.webhook_url,
    )

    return {
        "id": integration.id,
        "platform": "n8n",
        "workflow_id": integration.workflow_id,
        "webhook_url": integration.webhook_url,
        "active": integration.active,
        "created_at": integration.created_at.isoformat(),
    }


@router.get("/platforms")
async def list_platform_integrations(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """プラットフォーム連携一覧"""
    integrations = await automation_platform_manager.list_integrations(tenant_id)

    return {
        "zapier": [
            {
                "id": i.id,
                "zap_id": i.zap_id,
                "active": i.active,
                "created_at": i.created_at.isoformat(),
            }
            for i in integrations["zapier"]
        ],
        "make": [
            {
                "id": i.id,
                "scenario_id": i.scenario_id,
                "active": i.active,
                "created_at": i.created_at.isoformat(),
            }
            for i in integrations["make"]
        ],
        "n8n": [
            {
                "id": i.id,
                "workflow_id": i.workflow_id,
                "active": i.active,
                "created_at": i.created_at.isoformat(),
            }
            for i in integrations["n8n"]
        ],
    }


# =====================
# トリガーイベント情報
# =====================

@router.get("/events")
async def list_trigger_events():
    """利用可能なトリガーイベント一覧"""
    return {
        "events": [
            {
                "id": TriggerEvent.TRANSCRIPTION_COMPLETED.value,
                "name": "文字起こし完了",
                "description": "文字起こしが完了したときにトリガー",
            },
            {
                "id": TriggerEvent.TRANSCRIPTION_STARTED.value,
                "name": "文字起こし開始",
                "description": "文字起こしが開始されたときにトリガー",
            },
            {
                "id": TriggerEvent.SPEAKER_IDENTIFIED.value,
                "name": "話者識別完了",
                "description": "話者が識別されたときにトリガー",
            },
            {
                "id": TriggerEvent.ACTION_ITEM_CREATED.value,
                "name": "アクションアイテム作成",
                "description": "アクションアイテムが抽出されたときにトリガー",
            },
            {
                "id": TriggerEvent.SUMMARY_GENERATED.value,
                "name": "要約生成完了",
                "description": "会議要約が生成されたときにトリガー",
            },
            {
                "id": TriggerEvent.MEETING_ENDED.value,
                "name": "会議終了",
                "description": "会議が終了したときにトリガー",
            },
            {
                "id": TriggerEvent.KEYWORD_DETECTED.value,
                "name": "キーワード検出",
                "description": "設定したキーワードが検出されたときにトリガー",
            },
            {
                "id": TriggerEvent.SENTIMENT_ALERT.value,
                "name": "センチメントアラート",
                "description": "ネガティブな感情が検出されたときにトリガー",
            },
        ]
    }


# =====================
# 認証エンドポイント（外部プラットフォーム用）
# =====================

@router.post("/auth/validate")
async def validate_api_key_endpoint(
    x_api_key: str = Header(...),
):
    """APIキーを検証（Zapier/Make認証用）"""
    api_key = await api_key_manager.validate_api_key(x_api_key)

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return {
        "valid": True,
        "tenant_id": api_key.tenant_id,
        "scopes": api_key.scopes,
    }
