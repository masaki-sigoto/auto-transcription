"""高度なコンテンツ生成サービス"""

import os
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import httpx


class ContentType(str, Enum):
    MEETING_MINUTES = "meeting_minutes"
    SUMMARY = "summary"
    ACTION_ITEMS = "action_items"
    BLOG_POST = "blog_post"
    SOCIAL_MEDIA = "social_media"
    EMAIL = "email"
    PRESENTATION = "presentation"
    FAQ = "faq"
    NEWSLETTER = "newsletter"


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"
    JSON = "json"
    DOCX = "docx"
    PDF = "pdf"


@dataclass
class GeneratedContent:
    """生成されたコンテンツ"""
    id: str
    content_type: ContentType
    title: str
    content: str
    format: OutputFormat
    source_transcription_id: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    word_count: int = 0
    tokens_used: int = 0


@dataclass
class MeetingMinutes:
    """議事録"""
    title: str
    date: str
    attendees: List[str]
    agenda: List[str]
    discussion_points: List[Dict[str, Any]]
    decisions: List[str]
    action_items: List[Dict[str, Any]]
    next_steps: List[str]
    summary: str


@dataclass
class SocialMediaPost:
    """SNS投稿"""
    platform: str  # twitter, linkedin, facebook, instagram
    content: str
    hashtags: List[str]
    character_count: int
    suggested_images: List[str]


@dataclass
class EmailDraft:
    """メールドラフト"""
    subject: str
    body: str
    recipients: List[str]
    cc: List[str]
    tone: str  # formal, casual, friendly


class ContentGenerator:
    """コンテンツ生成エンジン"""

    def __init__(self, openai_api_key: Optional[str] = None):
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._generated: Dict[str, GeneratedContent] = {}

    async def generate_meeting_minutes(
        self,
        transcription_data: Dict[str, Any],
        template: Optional[str] = None,
        language: str = "ja",
    ) -> MeetingMinutes:
        """議事録を生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        # 話者リストを抽出
        speakers = list(set(s.get("speaker_id", "不明") for s in segments if s.get("speaker_id")))

        # AIで議事録を生成
        prompt = f"""以下の会議の文字起こしから、構造化された議事録を作成してください。

文字起こし:
{full_text[:3000]}

以下の形式でJSON形式で出力してください:
{{
    "title": "会議タイトル",
    "summary": "会議の要約（2-3文）",
    "agenda": ["議題1", "議題2"],
    "discussion_points": [
        {{"topic": "トピック", "details": "詳細", "speaker": "話者"}}
    ],
    "decisions": ["決定事項1", "決定事項2"],
    "action_items": [
        {{"task": "タスク", "assignee": "担当者", "deadline": "期限"}}
    ],
    "next_steps": ["次のステップ1", "次のステップ2"]
}}
"""

        # シミュレーション（実際はOpenAI APIを呼び出す）
        minutes = MeetingMinutes(
            title=transcription_data.get("title", "会議"),
            date=datetime.utcnow().strftime("%Y-%m-%d"),
            attendees=speakers if speakers else ["参加者1", "参加者2"],
            agenda=["進捗報告", "課題共有", "今後の予定"],
            discussion_points=[
                {"topic": "プロジェクト進捗", "details": "順調に進行中", "speaker": "話者1"},
            ],
            decisions=["次回は来週月曜日に開催"],
            action_items=[
                {"task": "資料作成", "assignee": "田中", "deadline": "金曜日まで"},
            ],
            next_steps=["進捗確認", "レビュー実施"],
            summary=full_text[:200] + "..." if len(full_text) > 200 else full_text,
        )

        return minutes

    async def generate_summary(
        self,
        transcription_data: Dict[str, Any],
        max_length: int = 500,
        style: str = "concise",
    ) -> str:
        """要約を生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        # シミュレーション
        if len(full_text) > max_length:
            return full_text[:max_length] + "..."
        return full_text

    async def extract_action_items(
        self,
        transcription_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """アクションアイテムを抽出"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        # キーワードベースの抽出（実際はAIを使用）
        action_keywords = ["します", "やります", "対応します", "確認します", "報告します"]

        action_items = []
        for i, seg in enumerate(segments):
            text = seg.get("text", "")
            for kw in action_keywords:
                if kw in text:
                    action_items.append({
                        "id": str(uuid.uuid4()),
                        "task": text,
                        "speaker": seg.get("speaker_id", "不明"),
                        "timestamp_ms": seg.get("start_time_ms", 0),
                        "priority": "medium",
                    })
                    break

        return action_items[:10]  # 最大10件

    async def generate_blog_post(
        self,
        transcription_data: Dict[str, Any],
        title: Optional[str] = None,
        style: str = "informative",
        target_audience: str = "general",
    ) -> Dict[str, Any]:
        """ブログ記事を生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        # シミュレーション
        blog = {
            "title": title or f"会議レポート: {datetime.utcnow().strftime('%Y-%m-%d')}",
            "introduction": f"今回の会議では、以下の内容について話し合いました。\n\n{full_text[:200]}...",
            "sections": [
                {"heading": "主なトピック", "content": "会議の主要なトピックについて..."},
                {"heading": "議論のポイント", "content": "参加者からの意見..."},
                {"heading": "まとめ", "content": "今回の会議のまとめ..."},
            ],
            "conclusion": "次回の会議に向けて、引き続き準備を進めていきます。",
            "tags": ["会議", "レポート", "ビジネス"],
            "word_count": len(full_text.split()),
            "estimated_read_time_min": max(1, len(full_text.split()) // 200),
        }

        return blog

    async def generate_social_media_posts(
        self,
        transcription_data: Dict[str, Any],
        platforms: List[str] = None,
    ) -> List[SocialMediaPost]:
        """SNS投稿を生成"""
        platforms = platforms or ["twitter", "linkedin"]
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)[:500]

        posts = []

        if "twitter" in platforms:
            content = f"📝 {full_text[:200]}..."
            posts.append(SocialMediaPost(
                platform="twitter",
                content=content[:280],
                hashtags=["#会議", "#ビジネス"],
                character_count=len(content[:280]),
                suggested_images=["meeting.jpg"],
            ))

        if "linkedin" in platforms:
            content = f"【会議レポート】\n\n{full_text[:400]}..."
            posts.append(SocialMediaPost(
                platform="linkedin",
                content=content,
                hashtags=["#ビジネス", "#プロフェッショナル"],
                character_count=len(content),
                suggested_images=["professional_meeting.jpg"],
            ))

        return posts

    async def generate_email_draft(
        self,
        transcription_data: Dict[str, Any],
        email_type: str = "summary",
        recipients: List[str] = None,
        tone: str = "formal",
    ) -> EmailDraft:
        """メールドラフトを生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        if email_type == "summary":
            subject = f"会議のサマリー - {datetime.utcnow().strftime('%Y/%m/%d')}"
            body = f"""お疲れ様です。

先ほどの会議内容をお送りいたします。

【要約】
{full_text[:300]}...

【決定事項】
- 引き続き進捗を確認する
- 次回は来週開催予定

ご不明な点がございましたら、お知らせください。

よろしくお願いいたします。
"""
        elif email_type == "follow_up":
            subject = f"【フォローアップ】会議について"
            body = f"""お疲れ様です。

先日の会議のフォローアップです。

{full_text[:200]}...

ご確認をお願いいたします。
"""
        else:
            subject = "会議について"
            body = full_text[:500]

        return EmailDraft(
            subject=subject,
            body=body,
            recipients=recipients or [],
            cc=[],
            tone=tone,
        )

    async def generate_presentation_outline(
        self,
        transcription_data: Dict[str, Any],
        num_slides: int = 10,
    ) -> Dict[str, Any]:
        """プレゼン資料のアウトラインを生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        slides = [
            {
                "slide_number": 1,
                "title": "タイトルスライド",
                "type": "title",
                "content": transcription_data.get("title", "プレゼンテーション"),
                "speaker_notes": "開始の挨拶",
            },
            {
                "slide_number": 2,
                "title": "アジェンダ",
                "type": "agenda",
                "content": ["トピック1", "トピック2", "トピック3"],
                "speaker_notes": "本日の流れを説明",
            },
        ]

        # コンテンツスライドを追加
        for i in range(3, min(num_slides, 9)):
            slides.append({
                "slide_number": i,
                "title": f"ポイント {i-2}",
                "type": "content",
                "content": f"内容: {full_text[(i-3)*100:(i-2)*100]}...",
                "speaker_notes": "詳細を説明",
            })

        slides.append({
            "slide_number": len(slides) + 1,
            "title": "まとめ",
            "type": "summary",
            "content": ["要点1", "要点2", "要点3"],
            "speaker_notes": "締めくくり",
        })

        return {
            "title": transcription_data.get("title", "プレゼンテーション"),
            "slides": slides,
            "estimated_duration_min": num_slides * 2,
            "template_suggestion": "professional_blue",
        }

    async def generate_faq(
        self,
        transcription_data: Dict[str, Any],
        num_questions: int = 5,
    ) -> List[Dict[str, str]]:
        """FAQを生成"""
        segments = transcription_data.get("segments", [])

        # 質問を抽出（?で終わるセグメント）
        questions = []
        for seg in segments:
            text = seg.get("text", "")
            if "?" in text or "？" in text:
                questions.append({
                    "question": text,
                    "answer": "この質問への回答は会議内で議論されました。",
                    "category": "一般",
                })

        # 質問がない場合はサンプルを生成
        if not questions:
            questions = [
                {"question": "このプロジェクトの目的は？", "answer": "...", "category": "概要"},
                {"question": "スケジュールはどうなっていますか？", "answer": "...", "category": "スケジュール"},
            ]

        return questions[:num_questions]

    async def generate_newsletter(
        self,
        transcription_data: Dict[str, Any],
        newsletter_name: str = "週刊レポート",
    ) -> Dict[str, Any]:
        """ニュースレターを生成"""
        segments = transcription_data.get("segments", [])
        full_text = " ".join(s.get("text", "") for s in segments)

        return {
            "title": newsletter_name,
            "date": datetime.utcnow().strftime("%Y年%m月%d日"),
            "header": {
                "image_url": None,
                "headline": transcription_data.get("title", "今週のハイライト"),
            },
            "sections": [
                {
                    "title": "トップニュース",
                    "content": full_text[:300] + "...",
                },
                {
                    "title": "今週のアクション",
                    "content": "チームの今週のアクションアイテム...",
                },
            ],
            "footer": {
                "unsubscribe_link": "#",
                "contact_email": "newsletter@example.com",
            },
        }


class TemplateEngine:
    """テンプレートエンジン"""

    def __init__(self):
        self._templates: Dict[str, str] = {
            "meeting_minutes_simple": """
# {title}

**日付**: {date}
**参加者**: {attendees}

## 議題
{agenda}

## 議論内容
{discussion}

## 決定事項
{decisions}

## アクションアイテム
{action_items}
""",
            "meeting_minutes_formal": """
# 議事録

## 会議情報
- **会議名**: {title}
- **開催日時**: {date}
- **参加者**: {attendees}

## 議題
{agenda}

## 議事内容
{discussion}

## 決定事項
{decisions}

## 宿題事項
{action_items}

## 次回会議
{next_meeting}

---
作成日: {created_at}
""",
        }

    def get_template(self, template_name: str) -> Optional[str]:
        """テンプレートを取得"""
        return self._templates.get(template_name)

    def list_templates(self) -> List[str]:
        """テンプレート一覧"""
        return list(self._templates.keys())

    def add_template(self, name: str, content: str):
        """テンプレートを追加"""
        self._templates[name] = content

    def render(self, template_name: str, data: Dict[str, Any]) -> str:
        """テンプレートをレンダリング"""
        template = self._templates.get(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")

        return template.format(**data)


# グローバルインスタンス
content_generator = ContentGenerator()
template_engine = TemplateEngine()
