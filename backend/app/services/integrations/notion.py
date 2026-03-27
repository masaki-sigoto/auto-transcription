import httpx
from typing import Optional
from datetime import datetime


class NotionClient:
    """Notion API クライアント"""

    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": self.API_VERSION,
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
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                json=data,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_user(self) -> dict:
        """認証ユーザー情報を取得"""
        return await self._request("GET", "/users/me")

    async def search_databases(self, query: str = "") -> list[dict]:
        """データベースを検索"""
        data = {
            "filter": {"property": "object", "value": "database"},
        }
        if query:
            data["query"] = query

        result = await self._request("POST", "/search", data)
        return result.get("results", [])

    async def create_page(
        self,
        parent_id: str,
        title: str,
        content_blocks: list[dict],
        parent_type: str = "database_id",
    ) -> dict:
        """ページを作成"""
        data = {
            "parent": {parent_type: parent_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            },
            "children": content_blocks,
        }

        return await self._request("POST", "/pages", data)

    async def append_blocks(self, page_id: str, blocks: list[dict]) -> dict:
        """ページにブロックを追加"""
        data = {"children": blocks}
        return await self._request("PATCH", f"/blocks/{page_id}/children", data)


class NotionBlockBuilder:
    """Notionブロック生成ヘルパー"""

    @staticmethod
    def heading_1(text: str) -> dict:
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def heading_2(text: str) -> dict:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def heading_3(text: str) -> dict:
        return {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def paragraph(text: str) -> dict:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def bulleted_list_item(text: str) -> dict:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def numbered_list_item(text: str) -> dict:
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    @staticmethod
    def to_do(text: str, checked: bool = False) -> dict:
        return {
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "checked": checked,
            },
        }

    @staticmethod
    def divider() -> dict:
        return {"object": "block", "type": "divider", "divider": {}}

    @staticmethod
    def callout(text: str, emoji: str = "📝") -> dict:
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji},
            },
        }


async def export_to_notion(
    access_token: str,
    database_id: str,
    title: str,
    summary: str,
    segments: list[dict],
    meeting_minutes: Optional[dict] = None,
) -> dict:
    """文字起こしをNotionにエクスポート"""
    client = NotionClient(access_token)
    builder = NotionBlockBuilder

    blocks = []

    # サマリー
    if summary:
        blocks.append(builder.callout(summary, "📋"))
        blocks.append(builder.divider())

    # 議事録がある場合
    if meeting_minutes:
        # 参加者
        if meeting_minutes.get("participants"):
            blocks.append(builder.heading_2("参加者"))
            for p in meeting_minutes["participants"]:
                blocks.append(builder.bulleted_list_item(p))

        # 議題
        if meeting_minutes.get("agenda_items"):
            blocks.append(builder.heading_2("議題"))
            for item in meeting_minutes["agenda_items"]:
                blocks.append(builder.heading_3(item.get("topic", "")))
                blocks.append(builder.paragraph(item.get("discussion", "")))
                if item.get("decisions"):
                    for decision in item["decisions"]:
                        blocks.append(builder.bulleted_list_item(f"決定: {decision}"))

        # アクションアイテム
        if meeting_minutes.get("action_items"):
            blocks.append(builder.heading_2("アクションアイテム"))
            for item in meeting_minutes["action_items"]:
                task = item.get("task", "")
                assignee = item.get("assignee", "")
                due = item.get("due_date", "")
                text = task
                if assignee:
                    text += f" (@{assignee})"
                if due:
                    text += f" - {due}"
                blocks.append(builder.to_do(text))

        blocks.append(builder.divider())

    # 文字起こし全文
    blocks.append(builder.heading_2("文字起こし"))
    for seg in segments[:100]:  # 最大100セグメント
        time_str = f"{seg['start_time_ms'] // 60000}:{(seg['start_time_ms'] // 1000) % 60:02d}"
        speaker = seg.get("speaker_label", "")
        text = seg.get("text", "")
        if speaker:
            blocks.append(builder.paragraph(f"[{time_str}] {speaker}: {text}"))
        else:
            blocks.append(builder.paragraph(f"[{time_str}] {text}"))

    # ページ作成
    page = await client.create_page(
        parent_id=database_id,
        title=title,
        content_blocks=blocks,
    )

    return page
