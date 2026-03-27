import httpx
from typing import Optional


class SlackClient:
    """Slack API クライアント"""

    BASE_URL = "https://slack.com/api"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
    ) -> dict:
        """APIリクエストを送信"""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.BASE_URL}/{endpoint}",
                headers=self.headers,
                json=data,
                timeout=30.0,
            )
            result = response.json()
            if not result.get("ok"):
                raise Exception(f"Slack API error: {result.get('error')}")
            return result

    async def get_user_info(self) -> dict:
        """認証ユーザー情報を取得"""
        return await self._request("GET", "auth.test")

    async def list_channels(self, types: str = "public_channel,private_channel") -> list[dict]:
        """チャンネル一覧を取得"""
        result = await self._request(
            "GET",
            f"conversations.list?types={types}&limit=200"
        )
        return result.get("channels", [])

    async def post_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[list[dict]] = None,
        thread_ts: Optional[str] = None,
    ) -> dict:
        """メッセージを投稿"""
        data = {
            "channel": channel,
            "text": text,
        }
        if blocks:
            data["blocks"] = blocks
        if thread_ts:
            data["thread_ts"] = thread_ts

        return await self._request("POST", "chat.postMessage", data)

    async def upload_file(
        self,
        channels: str,
        content: str,
        filename: str,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> dict:
        """ファイルをアップロード"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/files.upload",
                headers={"Authorization": f"Bearer {self.access_token}"},
                data={
                    "channels": channels,
                    "content": content,
                    "filename": filename,
                    "title": title or filename,
                    "initial_comment": initial_comment or "",
                },
                timeout=60.0,
            )
            result = response.json()
            if not result.get("ok"):
                raise Exception(f"Slack API error: {result.get('error')}")
            return result


class SlackBlockBuilder:
    """Slackブロック生成ヘルパー"""

    @staticmethod
    def header(text: str) -> dict:
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": text, "emoji": True},
        }

    @staticmethod
    def section(text: str) -> dict:
        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }

    @staticmethod
    def section_with_fields(fields: list[str]) -> dict:
        return {
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": f} for f in fields],
        }

    @staticmethod
    def divider() -> dict:
        return {"type": "divider"}

    @staticmethod
    def context(elements: list[str]) -> dict:
        return {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": e} for e in elements],
        }

    @staticmethod
    def actions(buttons: list[dict]) -> dict:
        return {
            "type": "actions",
            "elements": buttons,
        }

    @staticmethod
    def button(text: str, action_id: str, url: Optional[str] = None, style: Optional[str] = None) -> dict:
        btn = {
            "type": "button",
            "text": {"type": "plain_text", "text": text, "emoji": True},
            "action_id": action_id,
        }
        if url:
            btn["url"] = url
        if style:
            btn["style"] = style
        return btn


async def post_transcription_to_slack(
    access_token: str,
    channel: str,
    title: str,
    summary: str,
    duration_sec: int,
    transcription_url: str,
    meeting_minutes: Optional[dict] = None,
) -> dict:
    """文字起こし結果をSlackに投稿"""
    client = SlackClient(access_token)
    builder = SlackBlockBuilder

    blocks = [
        builder.header(f"📝 {title}"),
        builder.section(summary),
        builder.section_with_fields([
            f"*再生時間:*\n{duration_sec // 60}分{duration_sec % 60}秒",
            f"*ステータス:*\n✅ 完了",
        ]),
    ]

    # 議事録がある場合
    if meeting_minutes:
        blocks.append(builder.divider())

        # アクションアイテム
        if meeting_minutes.get("action_items"):
            action_text = "*📋 アクションアイテム:*\n"
            for item in meeting_minutes["action_items"][:5]:
                task = item.get("task", "")
                assignee = item.get("assignee", "")
                if assignee:
                    action_text += f"• {task} (@{assignee})\n"
                else:
                    action_text += f"• {task}\n"
            blocks.append(builder.section(action_text))

        # 次のステップ
        if meeting_minutes.get("next_steps"):
            next_text = "*🚀 次のステップ:*\n"
            for step in meeting_minutes["next_steps"][:3]:
                next_text += f"• {step}\n"
            blocks.append(builder.section(next_text))

    blocks.append(builder.divider())
    blocks.append(
        builder.actions([
            builder.button("詳細を見る", "view_transcription", url=transcription_url, style="primary"),
        ])
    )

    return await client.post_message(
        channel=channel,
        text=f"📝 文字起こし完了: {title}",
        blocks=blocks,
    )


async def upload_transcript_file(
    access_token: str,
    channel: str,
    title: str,
    transcript_text: str,
) -> dict:
    """文字起こしテキストをファイルとしてアップロード"""
    client = SlackClient(access_token)

    return await client.upload_file(
        channels=channel,
        content=transcript_text,
        filename=f"{title}.txt",
        title=title,
        initial_comment=f"📄 {title} の文字起こしファイル",
    )
