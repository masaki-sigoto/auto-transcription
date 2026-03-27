"""Slack/Teams/Discord連携APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.chat_platforms_service import (
    slack_integration,
    teams_integration,
    discord_integration,
    chat_platform_manager,
    ChatPlatform,
    MessageType,
)

router = APIRouter(prefix="/chat-platforms", tags=["chat-platforms"])


async def get_current_tenant_id() -> str:
    return "default-tenant"


# =====================
# Slack
# =====================

@router.get("/slack/auth/url")
async def get_slack_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Slack OAuth認証URLを取得"""
    auth_url = slack_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )

    return {"auth_url": auth_url, "platform": "slack"}


class SlackCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/slack/auth/callback")
async def slack_auth_callback(
    request: SlackCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Slack認証コールバック"""
    try:
        credentials = await slack_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )

        slack_integration.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "platform": "slack",
            "team_id": credentials.team_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/slack/auth/status")
async def get_slack_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Slack認証ステータス"""
    credentials = slack_integration.get_credentials(tenant_id)

    return {
        "authenticated": credentials is not None,
        "platform": "slack",
        "team_id": credentials.team_id if credentials else None,
    }


@router.get("/slack/channels")
async def list_slack_channels(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Slackチャンネル一覧"""
    try:
        channels = await slack_integration.list_channels(tenant_id)

        return {
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "is_private": ch.is_private,
                    "member_count": ch.member_count,
                }
                for ch in channels
            ],
            "count": len(channels),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class SlackMessageRequest(BaseModel):
    channel_id: str
    content: str
    thread_ts: Optional[str] = None


@router.post("/slack/messages")
async def send_slack_message(
    request: SlackMessageRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Slackメッセージ送信"""
    try:
        message = await slack_integration.send_message(
            tenant_id=tenant_id,
            channel_id=request.channel_id,
            content=request.content,
            thread_ts=request.thread_ts,
        )

        return {
            "message_id": message.id,
            "channel_id": message.channel_id,
            "timestamp": message.timestamp.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SlackTranscriptionRequest(BaseModel):
    channel_id: str
    transcription_id: str
    include_summary: bool = True


@router.post("/slack/transcription")
async def send_slack_transcription(
    request: SlackTranscriptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Slackに文字起こしを送信"""
    # 実際はDBから取得
    transcription_data = {
        "id": request.transcription_id,
        "title": "会議の文字起こし",
        "segments": [
            {"speaker_id": "話者1", "text": "サンプルテキストです。"},
            {"speaker_id": "話者2", "text": "これはテストです。"},
        ],
    }

    try:
        message = await slack_integration.send_transcription(
            tenant_id=tenant_id,
            channel_id=request.channel_id,
            transcription_data=transcription_data,
            include_summary=request.include_summary,
        )

        return {
            "message_id": message.id,
            "channel_id": message.channel_id,
            "status": "sent",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/slack/commands")
async def list_slack_commands():
    """Slackボットコマンド一覧"""
    commands = slack_integration.get_bot_commands()

    return {
        "commands": [
            {
                "name": cmd.name,
                "description": cmd.description,
                "usage": cmd.usage,
            }
            for cmd in commands
        ]
    }


# =====================
# Microsoft Teams
# =====================

@router.get("/teams/auth/url")
async def get_teams_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Teams OAuth認証URLを取得"""
    auth_url = teams_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        state=state,
    )

    return {"auth_url": auth_url, "platform": "teams"}


class TeamsCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/teams/auth/callback")
async def teams_auth_callback(
    request: TeamsCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teams認証コールバック"""
    try:
        credentials = await teams_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )

        teams_integration.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "platform": "teams",
            "team_id": credentials.team_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/teams/auth/status")
async def get_teams_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teams認証ステータス"""
    credentials = teams_integration.get_credentials(tenant_id)

    return {
        "authenticated": credentials is not None,
        "platform": "teams",
    }


@router.get("/teams/teams")
async def list_teams(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teams一覧"""
    try:
        teams = await teams_integration.list_teams(tenant_id)

        return {
            "teams": teams,
            "count": len(teams),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/teams/teams/{team_id}/channels")
async def list_teams_channels(
    team_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teamsチャンネル一覧"""
    try:
        channels = await teams_integration.list_channels(tenant_id, team_id)

        return {
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "member_count": ch.member_count,
                }
                for ch in channels
            ],
            "count": len(channels),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class TeamsMessageRequest(BaseModel):
    team_id: str
    channel_id: str
    content: str


@router.post("/teams/messages")
async def send_teams_message(
    request: TeamsMessageRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teamsメッセージ送信"""
    try:
        message = await teams_integration.send_message(
            tenant_id=tenant_id,
            team_id=request.team_id,
            channel_id=request.channel_id,
            content=request.content,
        )

        return {
            "message_id": message.id,
            "channel_id": message.channel_id,
            "timestamp": message.timestamp.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TeamsTranscriptionRequest(BaseModel):
    team_id: str
    channel_id: str
    transcription_id: str


@router.post("/teams/transcription")
async def send_teams_transcription(
    request: TeamsTranscriptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teamsに文字起こしを送信"""
    transcription_data = {
        "id": request.transcription_id,
        "title": "会議の文字起こし",
        "segments": [
            {"speaker_id": "話者1", "text": "サンプルテキストです。"},
        ],
    }

    try:
        message = await teams_integration.send_transcription_card(
            tenant_id=tenant_id,
            team_id=request.team_id,
            channel_id=request.channel_id,
            transcription_data=transcription_data,
        )

        return {
            "message_id": message.id,
            "status": "sent",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/teams/meetings/{meeting_id}/transcription")
async def get_teams_meeting_transcription(
    meeting_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Teams会議の文字起こしを取得"""
    try:
        transcription = await teams_integration.get_meeting_transcription(
            tenant_id=tenant_id,
            meeting_id=meeting_id,
        )

        return transcription
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================
# Discord
# =====================

@router.get("/discord/auth/url")
async def get_discord_auth_url(
    redirect_uri: str,
    permissions: int = 2048,
):
    """Discord OAuth認証URLを取得"""
    auth_url = discord_integration.get_oauth_url(
        redirect_uri=redirect_uri,
        permissions=permissions,
    )

    return {"auth_url": auth_url, "platform": "discord"}


class DiscordCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/discord/auth/callback")
async def discord_auth_callback(
    request: DiscordCallbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discord認証コールバック"""
    try:
        credentials = await discord_integration.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )

        discord_integration.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "platform": "discord",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/discord/auth/status")
async def get_discord_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discord認証ステータス"""
    credentials = discord_integration.get_credentials(tenant_id)

    return {
        "authenticated": credentials is not None,
        "platform": "discord",
    }


@router.get("/discord/guilds")
async def list_discord_guilds(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discordサーバー一覧"""
    try:
        guilds = await discord_integration.list_guilds(tenant_id)

        return {
            "guilds": guilds,
            "count": len(guilds),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/discord/guilds/{guild_id}/channels")
async def list_discord_channels(
    guild_id: str,
    channel_type: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discordチャンネル一覧"""
    try:
        channels = await discord_integration.list_channels(
            tenant_id, guild_id, channel_type
        )

        return {
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                }
                for ch in channels
            ],
            "count": len(channels),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class DiscordMessageRequest(BaseModel):
    channel_id: str
    content: str


@router.post("/discord/messages")
async def send_discord_message(
    request: DiscordMessageRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discordメッセージ送信"""
    try:
        message = await discord_integration.send_message(
            tenant_id=tenant_id,
            channel_id=request.channel_id,
            content=request.content,
        )

        return {
            "message_id": message.id,
            "channel_id": message.channel_id,
            "timestamp": message.timestamp.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DiscordVoiceTranscribeRequest(BaseModel):
    guild_id: str
    voice_channel_id: str
    output_channel_id: str


@router.post("/discord/voice/transcribe")
async def start_discord_voice_transcription(
    request: DiscordVoiceTranscribeRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discordボイスチャンネルの文字起こしを開始"""
    try:
        session = await discord_integration.start_voice_transcription(
            tenant_id=tenant_id,
            guild_id=request.guild_id,
            channel_id=request.voice_channel_id,
            output_channel_id=request.output_channel_id,
        )

        return session
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/discord/voice/stop")
async def stop_discord_voice_transcription(
    guild_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Discordボイスチャンネルの文字起こしを停止"""
    try:
        await discord_integration.leave_voice_channel(tenant_id, guild_id)

        return {"status": "stopped", "guild_id": guild_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/discord/commands")
async def list_discord_commands():
    """Discordスラッシュコマンド一覧"""
    commands = discord_integration.get_slash_commands()

    return {
        "commands": [
            {
                "name": cmd.name,
                "description": cmd.description,
                "usage": cmd.usage,
            }
            for cmd in commands
        ]
    }


# =====================
# 統合通知設定
# =====================

class SetupNotificationsRequest(BaseModel):
    platform: str
    channel_id: str
    events: List[str]
    team_id: Optional[str] = None


@router.post("/notifications/setup")
async def setup_notifications(
    request: SetupNotificationsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """通知設定をセットアップ"""
    try:
        platform = ChatPlatform(request.platform)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid platform: {request.platform}")

    config = await chat_platform_manager.setup_notifications(
        tenant_id=tenant_id,
        platform=platform,
        channel_id=request.channel_id,
        events=request.events,
        team_id=request.team_id,
    )

    return {
        "status": "configured",
        "platform": config["platform"].value,
        "channel_id": config["channel_id"],
        "events": config["events"],
    }


@router.get("/notifications/settings")
async def get_notification_settings(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """通知設定一覧"""
    settings = await chat_platform_manager.get_notification_settings(tenant_id)

    return {
        "settings": settings,
        "count": len(settings),
    }


class SendNotificationRequest(BaseModel):
    event_type: str
    data: dict


@router.post("/notifications/send")
async def send_notification(
    request: SendNotificationRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """通知を送信"""
    messages = await chat_platform_manager.send_notification(
        tenant_id=tenant_id,
        event_type=request.event_type,
        data=request.data,
    )

    return {
        "sent": len(messages),
        "messages": [
            {
                "platform": m.platform.value,
                "channel_id": m.channel_id,
                "message_id": m.id,
            }
            for m in messages
        ],
    }


@router.get("/notifications/events")
async def list_notification_events():
    """利用可能な通知イベント一覧"""
    return {
        "events": [
            {
                "id": "transcription_complete",
                "name": "文字起こし完了",
                "description": "文字起こしが完了した時に通知",
            },
            {
                "id": "action_items_extracted",
                "name": "アクションアイテム抽出",
                "description": "アクションアイテムが抽出された時に通知",
            },
            {
                "id": "summary_generated",
                "name": "要約生成",
                "description": "要約が生成された時に通知",
            },
            {
                "id": "meeting_started",
                "name": "会議開始",
                "description": "会議の文字起こしが開始された時に通知",
            },
            {
                "id": "meeting_ended",
                "name": "会議終了",
                "description": "会議の文字起こしが終了した時に通知",
            },
        ]
    }


# =====================
# プラットフォーム情報
# =====================

@router.get("/platforms")
async def list_platforms():
    """サポートされているプラットフォーム一覧"""
    return {
        "platforms": [
            {
                "id": "slack",
                "name": "Slack",
                "description": "Slackワークスペースと連携",
                "features": ["メッセージ送信", "ファイル共有", "スラッシュコマンド", "通知"],
            },
            {
                "id": "teams",
                "name": "Microsoft Teams",
                "description": "Microsoft Teamsと連携",
                "features": ["メッセージ送信", "Adaptive Cards", "会議文字起こし", "通知"],
            },
            {
                "id": "discord",
                "name": "Discord",
                "description": "Discordサーバーと連携",
                "features": ["メッセージ送信", "Embed", "ボイスチャンネル文字起こし", "スラッシュコマンド"],
            },
        ]
    }
