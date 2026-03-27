"""Zapier/Make/n8n自動化連携サービス"""

import uuid
import hmac
import hashlib
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class TriggerEvent(Enum):
    """トリガーイベントタイプ"""
    TRANSCRIPTION_COMPLETED = "transcription.completed"
    TRANSCRIPTION_STARTED = "transcription.started"
    SPEAKER_IDENTIFIED = "speaker.identified"
    ACTION_ITEM_CREATED = "action_item.created"
    SUMMARY_GENERATED = "summary.generated"
    MEETING_ENDED = "meeting.ended"
    KEYWORD_DETECTED = "keyword.detected"
    SENTIMENT_ALERT = "sentiment.alert"


class ActionType(Enum):
    """アクションタイプ"""
    CREATE_TRANSCRIPTION = "create_transcription"
    GET_TRANSCRIPTION = "get_transcription"
    EXPORT_TRANSCRIPTION = "export_transcription"
    UPDATE_SPEAKER = "update_speaker"
    CREATE_SUMMARY = "create_summary"
    SEARCH_CONTENT = "search_content"


@dataclass
class WebhookSubscription:
    """Webhook購読"""
    id: str
    tenant_id: str
    url: str
    events: List[TriggerEvent]
    secret: str
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_triggered: Optional[datetime] = None
    failure_count: int = 0


@dataclass
class WebhookDelivery:
    """Webhook配信ログ"""
    id: str
    subscription_id: str
    event: TriggerEvent
    payload: Dict[str, Any]
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    delivered_at: Optional[datetime] = None
    success: bool = False


class WebhookManager:
    """Webhook管理"""

    def __init__(self):
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._tenant_subscriptions: Dict[str, List[str]] = {}
        self._deliveries: Dict[str, WebhookDelivery] = {}

    async def create_subscription(
        self,
        tenant_id: str,
        url: str,
        events: List[str],
    ) -> WebhookSubscription:
        """Webhook購読を作成"""
        subscription_id = str(uuid.uuid4())
        secret = self._generate_secret()

        trigger_events = [TriggerEvent(e) for e in events]

        subscription = WebhookSubscription(
            id=subscription_id,
            tenant_id=tenant_id,
            url=url,
            events=trigger_events,
            secret=secret,
        )

        self._subscriptions[subscription_id] = subscription

        if tenant_id not in self._tenant_subscriptions:
            self._tenant_subscriptions[tenant_id] = []
        self._tenant_subscriptions[tenant_id].append(subscription_id)

        return subscription

    async def delete_subscription(self, subscription_id: str) -> bool:
        """Webhook購読を削除"""
        if subscription_id not in self._subscriptions:
            return False

        subscription = self._subscriptions[subscription_id]
        del self._subscriptions[subscription_id]

        if subscription.tenant_id in self._tenant_subscriptions:
            self._tenant_subscriptions[subscription.tenant_id] = [
                s for s in self._tenant_subscriptions[subscription.tenant_id]
                if s != subscription_id
            ]

        return True

    async def list_subscriptions(self, tenant_id: str) -> List[WebhookSubscription]:
        """Webhook購読一覧"""
        subscription_ids = self._tenant_subscriptions.get(tenant_id, [])
        return [
            self._subscriptions[sid]
            for sid in subscription_ids
            if sid in self._subscriptions
        ]

    async def trigger_webhooks(
        self,
        tenant_id: str,
        event: TriggerEvent,
        payload: Dict[str, Any],
    ) -> List[WebhookDelivery]:
        """Webhookをトリガー"""
        subscription_ids = self._tenant_subscriptions.get(tenant_id, [])
        deliveries = []

        for sub_id in subscription_ids:
            subscription = self._subscriptions.get(sub_id)
            if not subscription or not subscription.active:
                continue

            if event not in subscription.events:
                continue

            delivery = await self._deliver_webhook(subscription, event, payload)
            deliveries.append(delivery)

        return deliveries

    async def _deliver_webhook(
        self,
        subscription: WebhookSubscription,
        event: TriggerEvent,
        payload: Dict[str, Any],
    ) -> WebhookDelivery:
        """Webhookを配信"""
        delivery_id = str(uuid.uuid4())

        full_payload = {
            "event": event.value,
            "timestamp": datetime.utcnow().isoformat(),
            "data": payload,
        }

        # 署名を生成
        signature = self._generate_signature(subscription.secret, full_payload)

        delivery = WebhookDelivery(
            id=delivery_id,
            subscription_id=subscription.id,
            event=event,
            payload=full_payload,
        )

        # シミュレーション：実際のHTTPリクエストの代わり
        # 実際の実装ではhttpxやaiohttpを使用
        try:
            # 配信成功をシミュレート
            delivery.status_code = 200
            delivery.success = True
            delivery.delivered_at = datetime.utcnow()
            subscription.last_triggered = datetime.utcnow()
            subscription.failure_count = 0
        except Exception as e:
            delivery.status_code = 500
            delivery.response_body = str(e)
            delivery.success = False
            subscription.failure_count += 1

            # 連続失敗でサブスクリプションを無効化
            if subscription.failure_count >= 5:
                subscription.active = False

        self._deliveries[delivery_id] = delivery
        return delivery

    def _generate_secret(self) -> str:
        """Webhookシークレットを生成"""
        return f"whsec_{uuid.uuid4().hex}"

    def _generate_signature(self, secret: str, payload: Dict[str, Any]) -> str:
        """HMAC署名を生成"""
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        return hmac.new(
            secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

    async def verify_signature(
        self,
        subscription_id: str,
        payload: Dict[str, Any],
        signature: str,
    ) -> bool:
        """署名を検証"""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return False

        expected = self._generate_signature(subscription.secret, payload)
        return hmac.compare_digest(expected, signature)

    async def get_delivery_logs(
        self,
        subscription_id: str,
        limit: int = 50,
    ) -> List[WebhookDelivery]:
        """配信ログを取得"""
        logs = [
            d for d in self._deliveries.values()
            if d.subscription_id == subscription_id
        ]
        logs.sort(key=lambda x: x.delivered_at or datetime.min, reverse=True)
        return logs[:limit]


@dataclass
class APIKey:
    """APIキー"""
    id: str
    tenant_id: str
    name: str
    key_hash: str
    prefix: str
    scopes: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active: bool = True


class APIKeyManager:
    """APIキー管理（Zapier/Make認証用）"""

    def __init__(self):
        self._keys: Dict[str, APIKey] = {}
        self._tenant_keys: Dict[str, List[str]] = {}
        self._key_lookup: Dict[str, str] = {}  # prefix -> key_id

    async def create_api_key(
        self,
        tenant_id: str,
        name: str,
        scopes: List[str],
        expires_at: Optional[datetime] = None,
    ) -> tuple[APIKey, str]:
        """APIキーを作成（キーは一度のみ返される）"""
        key_id = str(uuid.uuid4())
        raw_key = f"sk_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
        prefix = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = APIKey(
            id=key_id,
            tenant_id=tenant_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes,
            expires_at=expires_at,
        )

        self._keys[key_id] = api_key
        self._key_lookup[prefix] = key_id

        if tenant_id not in self._tenant_keys:
            self._tenant_keys[tenant_id] = []
        self._tenant_keys[tenant_id].append(key_id)

        return api_key, raw_key

    async def validate_api_key(self, raw_key: str) -> Optional[APIKey]:
        """APIキーを検証"""
        if not raw_key.startswith("sk_"):
            return None

        prefix = raw_key[:12]
        key_id = self._key_lookup.get(prefix)

        if not key_id:
            return None

        api_key = self._keys.get(key_id)
        if not api_key:
            return None

        if not api_key.active:
            return None

        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        # ハッシュを検証
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        if not hmac.compare_digest(key_hash, api_key.key_hash):
            return None

        api_key.last_used = datetime.utcnow()
        return api_key

    async def revoke_api_key(self, key_id: str) -> bool:
        """APIキーを無効化"""
        if key_id not in self._keys:
            return False

        self._keys[key_id].active = False
        return True

    async def list_api_keys(self, tenant_id: str) -> List[APIKey]:
        """APIキー一覧"""
        key_ids = self._tenant_keys.get(tenant_id, [])
        return [self._keys[kid] for kid in key_ids if kid in self._keys]


@dataclass
class WorkflowTemplate:
    """ワークフローテンプレート"""
    id: str
    name: str
    description: str
    platform: str  # zapier, make, n8n
    trigger: TriggerEvent
    actions: List[Dict[str, Any]]
    config_schema: Dict[str, Any]


class WorkflowTemplateLibrary:
    """ワークフローテンプレートライブラリ"""

    def __init__(self):
        self._templates: Dict[str, WorkflowTemplate] = {}
        self._init_default_templates()

    def _init_default_templates(self):
        """デフォルトテンプレートを初期化"""
        templates = [
            WorkflowTemplate(
                id="slack-transcription-complete",
                name="文字起こし完了時にSlack通知",
                description="文字起こしが完了したらSlackチャンネルに通知",
                platform="zapier",
                trigger=TriggerEvent.TRANSCRIPTION_COMPLETED,
                actions=[
                    {"type": "slack.post_message", "channel": "{{channel}}"}
                ],
                config_schema={
                    "channel": {"type": "string", "required": True},
                },
            ),
            WorkflowTemplate(
                id="notion-action-items",
                name="アクションアイテムをNotionに追加",
                description="会議のアクションアイテムをNotionデータベースに自動追加",
                platform="make",
                trigger=TriggerEvent.ACTION_ITEM_CREATED,
                actions=[
                    {"type": "notion.create_page", "database_id": "{{database_id}}"}
                ],
                config_schema={
                    "database_id": {"type": "string", "required": True},
                },
            ),
            WorkflowTemplate(
                id="email-summary",
                name="会議要約をメール送信",
                description="会議終了後に参加者へ要約メールを送信",
                platform="n8n",
                trigger=TriggerEvent.SUMMARY_GENERATED,
                actions=[
                    {"type": "email.send", "to": "{{attendees}}"}
                ],
                config_schema={
                    "include_action_items": {"type": "boolean", "default": True},
                },
            ),
            WorkflowTemplate(
                id="crm-call-log",
                name="CRMに通話ログを追加",
                description="通話終了後にSalesforce/HubSpotにログを追加",
                platform="zapier",
                trigger=TriggerEvent.MEETING_ENDED,
                actions=[
                    {"type": "crm.create_activity", "crm": "{{crm_provider}}"}
                ],
                config_schema={
                    "crm_provider": {"type": "string", "enum": ["salesforce", "hubspot"]},
                },
            ),
            WorkflowTemplate(
                id="keyword-alert",
                name="キーワード検知アラート",
                description="特定のキーワードが検知されたら通知",
                platform="make",
                trigger=TriggerEvent.KEYWORD_DETECTED,
                actions=[
                    {"type": "notification.send", "method": "{{method}}"}
                ],
                config_schema={
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "method": {"type": "string", "enum": ["email", "slack", "webhook"]},
                },
            ),
            WorkflowTemplate(
                id="sentiment-escalation",
                name="ネガティブセンチメント対応",
                description="ネガティブな感情が検知されたらエスカレーション",
                platform="n8n",
                trigger=TriggerEvent.SENTIMENT_ALERT,
                actions=[
                    {"type": "ticket.create", "system": "{{ticket_system}}"}
                ],
                config_schema={
                    "threshold": {"type": "number", "default": -0.5},
                    "ticket_system": {"type": "string", "enum": ["jira", "zendesk"]},
                },
            ),
        ]

        for template in templates:
            self._templates[template.id] = template

    async def list_templates(
        self,
        platform: Optional[str] = None,
        trigger: Optional[TriggerEvent] = None,
    ) -> List[WorkflowTemplate]:
        """テンプレート一覧"""
        templates = list(self._templates.values())

        if platform:
            templates = [t for t in templates if t.platform == platform]

        if trigger:
            templates = [t for t in templates if t.trigger == trigger]

        return templates

    async def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """テンプレートを取得"""
        return self._templates.get(template_id)


@dataclass
class CustomWorkflow:
    """カスタムワークフロー"""
    id: str
    tenant_id: str
    name: str
    description: str
    trigger: TriggerEvent
    trigger_config: Dict[str, Any]
    actions: List[Dict[str, Any]]
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    execution_count: int = 0
    last_executed: Optional[datetime] = None


class CustomWorkflowEngine:
    """カスタムワークフローエンジン"""

    def __init__(self, webhook_manager: WebhookManager):
        self._workflows: Dict[str, CustomWorkflow] = {}
        self._tenant_workflows: Dict[str, List[str]] = {}
        self._webhook_manager = webhook_manager

    async def create_workflow(
        self,
        tenant_id: str,
        name: str,
        description: str,
        trigger: str,
        trigger_config: Dict[str, Any],
        actions: List[Dict[str, Any]],
    ) -> CustomWorkflow:
        """カスタムワークフローを作成"""
        workflow_id = str(uuid.uuid4())

        workflow = CustomWorkflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            trigger=TriggerEvent(trigger),
            trigger_config=trigger_config,
            actions=actions,
        )

        self._workflows[workflow_id] = workflow

        if tenant_id not in self._tenant_workflows:
            self._tenant_workflows[tenant_id] = []
        self._tenant_workflows[tenant_id].append(workflow_id)

        return workflow

    async def update_workflow(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_config: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        active: Optional[bool] = None,
    ) -> Optional[CustomWorkflow]:
        """ワークフローを更新"""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None

        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if trigger_config is not None:
            workflow.trigger_config = trigger_config
        if actions is not None:
            workflow.actions = actions
        if active is not None:
            workflow.active = active

        workflow.updated_at = datetime.utcnow()
        return workflow

    async def delete_workflow(self, workflow_id: str) -> bool:
        """ワークフローを削除"""
        if workflow_id not in self._workflows:
            return False

        workflow = self._workflows[workflow_id]
        del self._workflows[workflow_id]

        if workflow.tenant_id in self._tenant_workflows:
            self._tenant_workflows[workflow.tenant_id] = [
                w for w in self._tenant_workflows[workflow.tenant_id]
                if w != workflow_id
            ]

        return True

    async def list_workflows(self, tenant_id: str) -> List[CustomWorkflow]:
        """ワークフロー一覧"""
        workflow_ids = self._tenant_workflows.get(tenant_id, [])
        return [
            self._workflows[wid]
            for wid in workflow_ids
            if wid in self._workflows
        ]

    async def execute_workflows(
        self,
        tenant_id: str,
        event: TriggerEvent,
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """イベントに対応するワークフローを実行"""
        workflow_ids = self._tenant_workflows.get(tenant_id, [])
        results = []

        for wid in workflow_ids:
            workflow = self._workflows.get(wid)
            if not workflow or not workflow.active:
                continue

            if workflow.trigger != event:
                continue

            # トリガー条件をチェック
            if not self._check_trigger_conditions(workflow, data):
                continue

            result = await self._execute_workflow(workflow, data)
            results.append(result)

        return results

    def _check_trigger_conditions(
        self,
        workflow: CustomWorkflow,
        data: Dict[str, Any],
    ) -> bool:
        """トリガー条件をチェック"""
        config = workflow.trigger_config

        # キーワードフィルタ
        if "keywords" in config:
            content = data.get("content", "")
            if not any(kw in content for kw in config["keywords"]):
                return False

        # 最小時間フィルタ
        if "min_duration" in config:
            duration = data.get("duration_sec", 0)
            if duration < config["min_duration"]:
                return False

        # センチメントしきい値
        if "sentiment_threshold" in config:
            sentiment = data.get("sentiment_score", 0)
            if sentiment > config["sentiment_threshold"]:
                return False

        return True

    async def _execute_workflow(
        self,
        workflow: CustomWorkflow,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """ワークフローを実行"""
        workflow.execution_count += 1
        workflow.last_executed = datetime.utcnow()

        action_results = []

        for action in workflow.actions:
            action_type = action.get("type")
            action_config = action.get("config", {})

            # アクションを実行（シミュレーション）
            result = await self._execute_action(action_type, action_config, data)
            action_results.append(result)

        return {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "executed_at": datetime.utcnow().isoformat(),
            "actions": action_results,
            "success": all(r.get("success", False) for r in action_results),
        }

    async def _execute_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """アクションを実行"""
        # 実際の実装では各種サービスとの連携を行う
        return {
            "type": action_type,
            "config": config,
            "success": True,
            "executed_at": datetime.utcnow().isoformat(),
        }


@dataclass
class ZapierIntegration:
    """Zapier統合設定"""
    id: str
    tenant_id: str
    zap_id: str
    trigger_url: str
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MakeIntegration:
    """Make（Integromat）統合設定"""
    id: str
    tenant_id: str
    scenario_id: str
    webhook_url: str
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class N8nIntegration:
    """n8n統合設定"""
    id: str
    tenant_id: str
    workflow_id: str
    webhook_url: str
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


class AutomationPlatformManager:
    """自動化プラットフォーム管理"""

    def __init__(self, webhook_manager: WebhookManager):
        self._zapier_integrations: Dict[str, ZapierIntegration] = {}
        self._make_integrations: Dict[str, MakeIntegration] = {}
        self._n8n_integrations: Dict[str, N8nIntegration] = {}
        self._webhook_manager = webhook_manager

    async def setup_zapier(
        self,
        tenant_id: str,
        zap_id: str,
        trigger_url: str,
    ) -> ZapierIntegration:
        """Zapier統合をセットアップ"""
        integration_id = str(uuid.uuid4())

        integration = ZapierIntegration(
            id=integration_id,
            tenant_id=tenant_id,
            zap_id=zap_id,
            trigger_url=trigger_url,
        )

        self._zapier_integrations[integration_id] = integration

        # Webhookサブスクリプションを作成
        await self._webhook_manager.create_subscription(
            tenant_id=tenant_id,
            url=trigger_url,
            events=[e.value for e in TriggerEvent],
        )

        return integration

    async def setup_make(
        self,
        tenant_id: str,
        scenario_id: str,
        webhook_url: str,
    ) -> MakeIntegration:
        """Make統合をセットアップ"""
        integration_id = str(uuid.uuid4())

        integration = MakeIntegration(
            id=integration_id,
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            webhook_url=webhook_url,
        )

        self._make_integrations[integration_id] = integration

        await self._webhook_manager.create_subscription(
            tenant_id=tenant_id,
            url=webhook_url,
            events=[e.value for e in TriggerEvent],
        )

        return integration

    async def setup_n8n(
        self,
        tenant_id: str,
        workflow_id: str,
        webhook_url: str,
    ) -> N8nIntegration:
        """n8n統合をセットアップ"""
        integration_id = str(uuid.uuid4())

        integration = N8nIntegration(
            id=integration_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            webhook_url=webhook_url,
        )

        self._n8n_integrations[integration_id] = integration

        await self._webhook_manager.create_subscription(
            tenant_id=tenant_id,
            url=webhook_url,
            events=[e.value for e in TriggerEvent],
        )

        return integration

    async def list_integrations(
        self,
        tenant_id: str,
    ) -> Dict[str, List]:
        """統合一覧"""
        return {
            "zapier": [
                i for i in self._zapier_integrations.values()
                if i.tenant_id == tenant_id
            ],
            "make": [
                i for i in self._make_integrations.values()
                if i.tenant_id == tenant_id
            ],
            "n8n": [
                i for i in self._n8n_integrations.values()
                if i.tenant_id == tenant_id
            ],
        }


# グローバルインスタンス
webhook_manager = WebhookManager()
api_key_manager = APIKeyManager()
workflow_templates = WorkflowTemplateLibrary()
custom_workflow_engine = CustomWorkflowEngine(webhook_manager)
automation_platform_manager = AutomationPlatformManager(webhook_manager)
