"""Slack/Teams/Discord連携サービス"""

import os
import uuid
import hmac
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import json


class ChatPlatform(str, Enum):
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"


class MessageType(str, Enum):
    TEXT = "text"
    TRANSCRIPTION = "transcription"
    SUMMARY = "summary"
    ACTION_ITEMS = "action_items"
    NOTIFICATION = "notification"


@dataclass
class PlatformCredentials:
    """プラットフォーム認証情報"""
    platform: ChatPlatform
    access_token: str
    refresh_token: Optional[str] = None
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    team_id: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass
class Channel:
    """チャンネル情報"""
    id: str
    name: str
    platform: ChatPlatform
    is_private: bool = False
    member_count: int = 0


@dataclass
class Message:
    """メッセージ"""
    id: str
    channel_id: str
    content: str
    message_type: MessageType
    platform: ChatPlatform
    timestamp: datetime
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BotCommand:
    """ボットコマンド"""
    name: str
    description: str
    usage: str
    handler: str


# =====================
# Slack連携
# =====================

class SlackIntegration:
    """Slack連携"""

    def __init__(self):
        self.client_id = os.getenv("SLACK_CLIENT_ID", "")
        self.client_secret = os.getenv("SLACK_CLIENT_SECRET", "")
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
        self._credentials: Dict[str, PlatformCredentials] = {}
        self._channels: Dict[str, List[Channel]] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or [
            "channels:read",
            "channels:history",
            "chat:write",
            "files:write",
            "users:read",
            "commands",
        ]

        scope_str = ",".join(scopes)
        auth_url = (
            f"https://slack.com/oauth/v2/authorize?"
            f"client_id={self.client_id}"
            f"&scope={scope_str}"
            f"&redirect_uri={redirect_uri}"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> PlatformCredentials:
        """認証コードをトークンに交換"""
        # シミュレーション
        credentials = PlatformCredentials(
            platform=ChatPlatform.SLACK,
            access_token=f"xoxb-{uuid.uuid4().hex[:20]}",
            bot_token=f"xoxb-{uuid.uuid4().hex[:20]}",
            team_id=f"T{uuid.uuid4().hex[:8].upper()}",
        )

        return credentials

    def store_credentials(self, tenant_id: str, credentials: PlatformCredentials):
        """認証情報を保存"""
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[PlatformCredentials]:
        """認証情報を取得"""
        return self._credentials.get(tenant_id)

    def verify_request(self, timestamp: str, signature: str, body: str) -> bool:
        """リクエスト署名を検証"""
        sig_basestring = f"v0:{timestamp}:{body}"
        my_signature = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(my_signature, signature)

    async def list_channels(self, tenant_id: str) -> List[Channel]:
        """チャンネル一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Slack")

        # シミュレーション
        if tenant_id not in self._channels:
            self._channels[tenant_id] = [
                Channel(id="C001", name="general", platform=ChatPlatform.SLACK, member_count=50),
                Channel(id="C002", name="transcriptions", platform=ChatPlatform.SLACK, member_count=20),
                Channel(id="C003", name="meetings", platform=ChatPlatform.SLACK, member_count=30),
            ]

        return self._channels[tenant_id]

    async def send_message(
        self,
        tenant_id: str,
        channel_id: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict]] = None,
    ) -> Message:
        """メッセージを送信"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Slack")

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            channel_id=channel_id,
            content=content,
            message_type=message_type,
            platform=ChatPlatform.SLACK,
            timestamp=datetime.utcnow(),
            thread_id=thread_ts,
        )

        return message

    async def send_transcription(
        self,
        tenant_id: str,
        channel_id: str,
        transcription_data: Dict[str, Any],
        include_summary: bool = True,
    ) -> Message:
        """文字起こしを送信"""
        title = transcription_data.get("title", "文字起こし")
        segments = transcription_data.get("segments", [])

        # Slackブロック形式で構築
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📝 {title}"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*セグメント数*: {len(segments)}\n*作成日時*: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
                }
            },
            {"type": "divider"},
        ]

        # セグメントを追加（最大10件）
        for seg in segments[:10]:
            speaker = seg.get("speaker_id", "不明")
            text = seg.get("text", "")
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{speaker}*: {text}"}
            })

        content = f"📝 {title} の文字起こしが完了しました"

        return await self.send_message(
            tenant_id=tenant_id,
            channel_id=channel_id,
            content=content,
            message_type=MessageType.TRANSCRIPTION,
            blocks=blocks,
        )

    async def send_action_items(
        self,
        tenant_id: str,
        channel_id: str,
        action_items: List[Dict[str, Any]],
        meeting_title: str = "会議",
    ) -> Message:
        """アクションアイテムを送信"""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"✅ {meeting_title} - アクションアイテム"}
            },
            {"type": "divider"},
        ]

        for item in action_items:
            task = item.get("task", "")
            assignee = item.get("assignee", "未割当")
            deadline = item.get("deadline", "未定")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• {task}\n  👤 担当: {assignee} | 📅 期限: {deadline}"
                }
            })

        content = f"✅ {meeting_title} のアクションアイテム ({len(action_items)}件)"

        return await self.send_message(
            tenant_id=tenant_id,
            channel_id=channel_id,
            content=content,
            message_type=MessageType.ACTION_ITEMS,
            blocks=blocks,
        )

    async def upload_file(
        self,
        tenant_id: str,
        channel_id: str,
        file_content: bytes,
        filename: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """ファイルをアップロード"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Slack")

        # シミュレーション
        return {
            "file_id": f"F{uuid.uuid4().hex[:10].upper()}",
            "filename": filename,
            "title": title or filename,
            "channel_id": channel_id,
            "url": f"https://files.slack.com/{filename}",
        }

    def get_bot_commands(self) -> List[BotCommand]:
        """ボットコマンド一覧"""
        return [
            BotCommand(
                name="/transcribe",
                description="音声ファイルを文字起こし",
                usage="/transcribe [ファイルURL]",
                handler="handle_transcribe"
            ),
            BotCommand(
                name="/search",
                description="文字起こしを検索",
                usage="/search [キーワード]",
                handler="handle_search"
            ),
            BotCommand(
                name="/summary",
                description="最新の文字起こしの要約を表示",
                usage="/summary [transcription_id]",
                handler="handle_summary"
            ),
            BotCommand(
                name="/actions",
                description="アクションアイテムを表示",
                usage="/actions [meeting_id]",
                handler="handle_actions"
            ),
        ]


# =====================
# Microsoft Teams連携
# =====================

class TeamsIntegration:
    """Microsoft Teams連携"""

    def __init__(self):
        self.client_id = os.getenv("TEAMS_CLIENT_ID", "")
        self.client_secret = os.getenv("TEAMS_CLIENT_SECRET", "")
        self.tenant_id = os.getenv("TEAMS_TENANT_ID", "")
        self._credentials: Dict[str, PlatformCredentials] = {}
        self._channels: Dict[str, List[Channel]] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or [
            "Channel.ReadBasic.All",
            "ChannelMessage.Send",
            "Team.ReadBasic.All",
            "User.Read",
            "OnlineMeetings.Read",
        ]

        scope_str = " ".join(scopes)
        auth_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize?"
            f"client_id={self.client_id}"
            f"&response_type=code"
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
    ) -> PlatformCredentials:
        """認証コードをトークンに交換"""
        # シミュレーション
        credentials = PlatformCredentials(
            platform=ChatPlatform.TEAMS,
            access_token=f"eyJ0eXAi_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
            team_id=f"team_{uuid.uuid4().hex[:8]}",
            expires_at=datetime.utcnow(),
        )

        return credentials

    def store_credentials(self, tenant_id: str, credentials: PlatformCredentials):
        """認証情報を保存"""
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[PlatformCredentials]:
        """認証情報を取得"""
        return self._credentials.get(tenant_id)

    async def list_teams(self, tenant_id: str) -> List[Dict[str, Any]]:
        """チーム一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Teams")

        # シミュレーション
        return [
            {"id": "team1", "name": "開発チーム", "description": "開発チームのチャンネル"},
            {"id": "team2", "name": "営業チーム", "description": "営業チームのチャンネル"},
        ]

    async def list_channels(self, tenant_id: str, team_id: str) -> List[Channel]:
        """チャンネル一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Teams")

        # シミュレーション
        return [
            Channel(id="ch1", name="General", platform=ChatPlatform.TEAMS, member_count=30),
            Channel(id="ch2", name="Meetings", platform=ChatPlatform.TEAMS, member_count=25),
        ]

    async def send_message(
        self,
        tenant_id: str,
        team_id: str,
        channel_id: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        adaptive_card: Optional[Dict] = None,
    ) -> Message:
        """メッセージを送信"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Teams")

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            channel_id=channel_id,
            content=content,
            message_type=message_type,
            platform=ChatPlatform.TEAMS,
            timestamp=datetime.utcnow(),
        )

        return message

    async def send_transcription_card(
        self,
        tenant_id: str,
        team_id: str,
        channel_id: str,
        transcription_data: Dict[str, Any],
    ) -> Message:
        """Adaptive Cardで文字起こしを送信"""
        title = transcription_data.get("title", "文字起こし")
        segments = transcription_data.get("segments", [])

        # Adaptive Card形式
        adaptive_card = {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"📝 {title}",
                    "size": "Large",
                    "weight": "Bolder"
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "セグメント数", "value": str(len(segments))},
                        {"title": "作成日時", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M")},
                    ]
                },
                {"type": "TextBlock", "text": "---"},
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "詳細を見る",
                    "url": f"https://app.example.com/transcription/{transcription_data.get('id', '')}"
                }
            ]
        }

        # セグメントを追加
        for seg in segments[:5]:
            speaker = seg.get("speaker_id", "不明")
            text = seg.get("text", "")
            adaptive_card["body"].append({
                "type": "TextBlock",
                "text": f"**{speaker}**: {text}",
                "wrap": True
            })

        content = f"📝 {title} の文字起こしが完了しました"

        return await self.send_message(
            tenant_id=tenant_id,
            team_id=team_id,
            channel_id=channel_id,
            content=content,
            message_type=MessageType.TRANSCRIPTION,
            adaptive_card=adaptive_card,
        )

    async def get_meeting_transcription(
        self,
        tenant_id: str,
        meeting_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Teams会議の文字起こしを取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Teams")

        # シミュレーション（実際はGraph APIを使用）
        return {
            "meeting_id": meeting_id,
            "transcription_available": True,
            "segments": [
                {"speaker": "User 1", "text": "会議を始めましょう。", "timestamp": "00:00:05"},
                {"speaker": "User 2", "text": "よろしくお願いします。", "timestamp": "00:00:10"},
            ],
        }


# =====================
# Discord連携
# =====================

class DiscordIntegration:
    """Discord連携"""

    def __init__(self):
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN", "")
        self._credentials: Dict[str, PlatformCredentials] = {}
        self._guilds: Dict[str, List[Dict]] = {}

    def get_oauth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        permissions: int = 2048,  # Send Messages
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or ["bot", "applications.commands"]
        scope_str = "%20".join(scopes)

        auth_url = (
            f"https://discord.com/api/oauth2/authorize?"
            f"client_id={self.client_id}"
            f"&permissions={permissions}"
            f"&scope={scope_str}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
        )

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> PlatformCredentials:
        """認証コードをトークンに交換"""
        # シミュレーション
        credentials = PlatformCredentials(
            platform=ChatPlatform.DISCORD,
            access_token=f"discord_{uuid.uuid4().hex[:30]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:20]}",
            bot_token=self.bot_token,
        )

        return credentials

    def store_credentials(self, tenant_id: str, credentials: PlatformCredentials):
        """認証情報を保存"""
        self._credentials[tenant_id] = credentials

    def get_credentials(self, tenant_id: str) -> Optional[PlatformCredentials]:
        """認証情報を取得"""
        return self._credentials.get(tenant_id)

    async def list_guilds(self, tenant_id: str) -> List[Dict[str, Any]]:
        """サーバー一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Discord")

        # シミュレーション
        return [
            {"id": "guild1", "name": "開発サーバー", "member_count": 100},
            {"id": "guild2", "name": "テストサーバー", "member_count": 50},
        ]

    async def list_channels(
        self,
        tenant_id: str,
        guild_id: str,
        channel_type: Optional[str] = None,  # text, voice
    ) -> List[Channel]:
        """チャンネル一覧を取得"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Discord")

        # シミュレーション
        channels = [
            Channel(id="ch1", name="general", platform=ChatPlatform.DISCORD),
            Channel(id="ch2", name="transcriptions", platform=ChatPlatform.DISCORD),
            Channel(id="vc1", name="Voice Channel 1", platform=ChatPlatform.DISCORD),
        ]

        return channels

    async def send_message(
        self,
        tenant_id: str,
        channel_id: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        embed: Optional[Dict] = None,
    ) -> Message:
        """メッセージを送信"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Discord")

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:18]}",
            channel_id=channel_id,
            content=content,
            message_type=message_type,
            platform=ChatPlatform.DISCORD,
            timestamp=datetime.utcnow(),
        )

        return message

    async def send_transcription_embed(
        self,
        tenant_id: str,
        channel_id: str,
        transcription_data: Dict[str, Any],
    ) -> Message:
        """Embedで文字起こしを送信"""
        title = transcription_data.get("title", "文字起こし")
        segments = transcription_data.get("segments", [])

        # Discord Embed形式
        embed = {
            "title": f"📝 {title}",
            "color": 0x5865F2,  # Discord Blurple
            "fields": [
                {"name": "セグメント数", "value": str(len(segments)), "inline": True},
                {"name": "作成日時", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "inline": True},
            ],
            "footer": {"text": "自動文字起こしシステム"},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # セグメントを追加
        transcript_text = ""
        for seg in segments[:5]:
            speaker = seg.get("speaker_id", "不明")
            text = seg.get("text", "")
            transcript_text += f"**{speaker}**: {text}\n"

        if transcript_text:
            embed["description"] = transcript_text

        content = f"📝 {title} の文字起こしが完了しました"

        return await self.send_message(
            tenant_id=tenant_id,
            channel_id=channel_id,
            content=content,
            message_type=MessageType.TRANSCRIPTION,
            embed=embed,
        )

    async def join_voice_channel(
        self,
        tenant_id: str,
        guild_id: str,
        channel_id: str,
    ) -> Dict[str, Any]:
        """ボイスチャンネルに参加"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Discord")

        # シミュレーション
        return {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "status": "connected",
            "session_id": str(uuid.uuid4()),
        }

    async def leave_voice_channel(
        self,
        tenant_id: str,
        guild_id: str,
    ) -> bool:
        """ボイスチャンネルから退出"""
        creds = self.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Discord")

        return True

    async def start_voice_transcription(
        self,
        tenant_id: str,
        guild_id: str,
        channel_id: str,
        output_channel_id: str,
    ) -> Dict[str, Any]:
        """ボイスチャンネルの文字起こしを開始"""
        # まずボイスチャンネルに参加
        await self.join_voice_channel(tenant_id, guild_id, channel_id)

        return {
            "session_id": str(uuid.uuid4()),
            "voice_channel_id": channel_id,
            "output_channel_id": output_channel_id,
            "status": "transcribing",
            "started_at": datetime.utcnow().isoformat(),
        }

    def get_slash_commands(self) -> List[BotCommand]:
        """スラッシュコマンド一覧"""
        return [
            BotCommand(
                name="/transcribe",
                description="添付された音声ファイルを文字起こし",
                usage="/transcribe",
                handler="handle_transcribe"
            ),
            BotCommand(
                name="/voice-transcribe",
                description="ボイスチャンネルの文字起こしを開始",
                usage="/voice-transcribe [channel]",
                handler="handle_voice_transcribe"
            ),
            BotCommand(
                name="/search",
                description="文字起こしを検索",
                usage="/search [query]",
                handler="handle_search"
            ),
            BotCommand(
                name="/summary",
                description="文字起こしの要約を表示",
                usage="/summary [id]",
                handler="handle_summary"
            ),
        ]


# =====================
# 統合マネージャー
# =====================

class ChatPlatformManager:
    """チャットプラットフォーム統合管理"""

    def __init__(self):
        self.slack = SlackIntegration()
        self.teams = TeamsIntegration()
        self.discord = DiscordIntegration()
        self._notification_settings: Dict[str, Dict[str, Any]] = {}

    def get_integration(self, platform: ChatPlatform):
        """プラットフォーム統合を取得"""
        if platform == ChatPlatform.SLACK:
            return self.slack
        elif platform == ChatPlatform.TEAMS:
            return self.teams
        elif platform == ChatPlatform.DISCORD:
            return self.discord
        else:
            raise ValueError(f"Unknown platform: {platform}")

    async def setup_notifications(
        self,
        tenant_id: str,
        platform: ChatPlatform,
        channel_id: str,
        events: List[str],
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通知設定をセットアップ"""
        config_id = f"{tenant_id}_{platform.value}"

        self._notification_settings[config_id] = {
            "tenant_id": tenant_id,
            "platform": platform,
            "channel_id": channel_id,
            "team_id": team_id,
            "events": events,
            "enabled": True,
            "created_at": datetime.utcnow(),
        }

        return self._notification_settings[config_id]

    async def send_notification(
        self,
        tenant_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> List[Message]:
        """通知を送信"""
        messages = []

        for config_id, config in self._notification_settings.items():
            if not config_id.startswith(tenant_id):
                continue

            if event_type not in config.get("events", []):
                continue

            if not config.get("enabled"):
                continue

            platform = config["platform"]
            channel_id = config["channel_id"]

            try:
                integration = self.get_integration(platform)

                if event_type == "transcription_complete":
                    if platform == ChatPlatform.SLACK:
                        msg = await integration.send_transcription(
                            tenant_id, channel_id, data
                        )
                    elif platform == ChatPlatform.TEAMS:
                        msg = await integration.send_transcription_card(
                            tenant_id, config.get("team_id"), channel_id, data
                        )
                    elif platform == ChatPlatform.DISCORD:
                        msg = await integration.send_transcription_embed(
                            tenant_id, channel_id, data
                        )
                    messages.append(msg)

                elif event_type == "action_items_extracted":
                    if platform == ChatPlatform.SLACK:
                        msg = await integration.send_action_items(
                            tenant_id, channel_id,
                            data.get("action_items", []),
                            data.get("meeting_title", "会議")
                        )
                        messages.append(msg)

            except Exception as e:
                print(f"Failed to send notification to {platform}: {e}")

        return messages

    async def get_notification_settings(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """通知設定一覧を取得"""
        settings = []
        for config_id, config in self._notification_settings.items():
            if config_id.startswith(tenant_id):
                settings.append({
                    "platform": config["platform"].value,
                    "channel_id": config["channel_id"],
                    "events": config["events"],
                    "enabled": config["enabled"],
                })
        return settings


# グローバルインスタンス
slack_integration = SlackIntegration()
teams_integration = TeamsIntegration()
discord_integration = DiscordIntegration()
chat_platform_manager = ChatPlatformManager()
