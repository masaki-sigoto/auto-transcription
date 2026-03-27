import json
from dataclasses import dataclass
from anthropic import Anthropic

from app.core.config import get_settings
from app.services.transcription_engine import TranscriptionSegment


@dataclass
class MeetingMinutes:
    """議事録"""
    title: str
    date: str
    participants: list[str]
    summary: str
    agenda_items: list[dict]  # {"topic": str, "discussion": str, "decisions": list[str]}
    action_items: list[dict]  # {"task": str, "assignee": str, "due_date": str}
    next_steps: list[str]
    raw_notes: str


@dataclass
class ContentSummary:
    """コンテンツ要約"""
    title: str
    summary: str
    key_points: list[str]
    topics: list[dict]  # {"name": str, "time_range": str, "description": str}
    keywords: list[str]
    sentiment: str  # positive, neutral, negative


class AISummaryService:
    """AI要約・議事録生成サービス"""

    MEETING_MINUTES_PROMPT = """あなたは優秀な議事録作成者です。以下の会議の文字起こしから、構造化された議事録を作成してください。

要件:
1. 会議の主題を特定してタイトルをつける
2. 参加者を特定（話者ラベルから推測）
3. 議題ごとに整理（トピック、議論内容、決定事項）
4. アクションアイテムを抽出（タスク、担当者、期限があれば）
5. 次のステップをまとめる

文字起こし:
{transcript}

---
以下のJSON形式で出力してください（日本語で）:
{{
    "title": "会議タイトル",
    "date": "推定日付（不明な場合は空）",
    "participants": ["参加者1", "参加者2"],
    "summary": "会議の概要（3-5文）",
    "agenda_items": [
        {{
            "topic": "議題",
            "discussion": "議論の要約",
            "decisions": ["決定事項1", "決定事項2"]
        }}
    ],
    "action_items": [
        {{
            "task": "タスク内容",
            "assignee": "担当者（不明なら空）",
            "due_date": "期限（不明なら空）"
        }}
    ],
    "next_steps": ["次のステップ1", "次のステップ2"]
}}"""

    CONTENT_SUMMARY_PROMPT = """以下の音声コンテンツの文字起こしを分析し、構造化された要約を作成してください。

要件:
1. コンテンツの主題を特定してタイトルをつける
2. 全体の要約を作成（3-5文）
3. 主要なポイントを箇条書きで抽出
4. トピックごとに整理（タイムスタンプ付き）
5. キーワードを抽出
6. 全体的なトーン/感情を判定

文字起こし:
{transcript}

---
以下のJSON形式で出力してください（日本語で）:
{{
    "title": "コンテンツタイトル",
    "summary": "全体の要約",
    "key_points": ["ポイント1", "ポイント2", "ポイント3"],
    "topics": [
        {{
            "name": "トピック名",
            "time_range": "0:00-5:30",
            "description": "トピックの説明"
        }}
    ],
    "keywords": ["キーワード1", "キーワード2"],
    "sentiment": "positive/neutral/negative"
}}"""

    CHAPTER_PROMPT = """以下の文字起こしを分析し、自然なチャプター（章立て）に分割してください。

要件:
1. トピックの変化を検出してチャプターを作成
2. 各チャプターにタイトルと概要をつける
3. 開始時間と終了時間を含める

文字起こし:
{transcript}

---
以下のJSON形式で出力してください:
{{
    "chapters": [
        {{
            "title": "チャプタータイトル",
            "start_time_ms": 0,
            "end_time_ms": 60000,
            "summary": "このチャプターの概要"
        }}
    ]
}}"""

    def __init__(self):
        settings = get_settings()
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    def _format_transcript(
        self, segments: list[TranscriptionSegment], include_speaker: bool = True
    ) -> str:
        """文字起こしをフォーマット"""
        lines = []
        for seg in segments:
            time_str = self._format_time(seg.start_time_ms)
            if include_speaker and seg.speaker_id:
                lines.append(f"[{time_str}] {seg.speaker_id}: {seg.text}")
            else:
                lines.append(f"[{time_str}] {seg.text}")
        return "\n".join(lines)

    def _format_time(self, ms: int) -> str:
        """ミリ秒を時刻文字列に変換"""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _call_llm(self, prompt: str, max_tokens: int = 4096) -> str:
        """LLMを呼び出し"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse_json_response(self, response: str) -> dict:
        """JSONレスポンスをパース"""
        # コードブロックを除去
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        return json.loads(response.strip())

    async def generate_meeting_minutes(
        self, segments: list[TranscriptionSegment]
    ) -> MeetingMinutes:
        """議事録を生成"""
        transcript = self._format_transcript(segments, include_speaker=True)
        prompt = self.MEETING_MINUTES_PROMPT.format(transcript=transcript)

        response = self._call_llm(prompt)
        data = self._parse_json_response(response)

        return MeetingMinutes(
            title=data.get("title", ""),
            date=data.get("date", ""),
            participants=data.get("participants", []),
            summary=data.get("summary", ""),
            agenda_items=data.get("agenda_items", []),
            action_items=data.get("action_items", []),
            next_steps=data.get("next_steps", []),
            raw_notes=transcript,
        )

    async def generate_content_summary(
        self, segments: list[TranscriptionSegment]
    ) -> ContentSummary:
        """コンテンツ要約を生成"""
        transcript = self._format_transcript(segments, include_speaker=False)
        prompt = self.CONTENT_SUMMARY_PROMPT.format(transcript=transcript)

        response = self._call_llm(prompt)
        data = self._parse_json_response(response)

        return ContentSummary(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            key_points=data.get("key_points", []),
            topics=data.get("topics", []),
            keywords=data.get("keywords", []),
            sentiment=data.get("sentiment", "neutral"),
        )

    async def generate_chapters(
        self, segments: list[TranscriptionSegment]
    ) -> list[dict]:
        """チャプターを生成"""
        transcript = self._format_transcript(segments, include_speaker=False)
        prompt = self.CHAPTER_PROMPT.format(transcript=transcript)

        response = self._call_llm(prompt)
        data = self._parse_json_response(response)

        return data.get("chapters", [])

    async def generate_qa_pairs(
        self, segments: list[TranscriptionSegment], num_pairs: int = 5
    ) -> list[dict]:
        """Q&Aペアを生成（学習用途）"""
        transcript = self._format_transcript(segments, include_speaker=False)

        prompt = f"""以下の文字起こしから、内容理解を確認するためのQ&Aペアを{num_pairs}個作成してください。

文字起こし:
{transcript}

---
以下のJSON形式で出力してください:
{{
    "qa_pairs": [
        {{
            "question": "質問",
            "answer": "回答",
            "source_time": "関連する時間帯"
        }}
    ]
}}"""

        response = self._call_llm(prompt)
        data = self._parse_json_response(response)

        return data.get("qa_pairs", [])

    async def extract_entities(
        self, segments: list[TranscriptionSegment]
    ) -> dict:
        """エンティティ（人名、組織、場所など）を抽出"""
        transcript = self._format_transcript(segments, include_speaker=False)

        prompt = f"""以下の文字起こしから、重要なエンティティ（固有名詞）を抽出してください。

文字起こし:
{transcript}

---
以下のJSON形式で出力してください:
{{
    "people": ["人名1", "人名2"],
    "organizations": ["組織名1", "組織名2"],
    "locations": ["場所1", "場所2"],
    "products": ["製品名1", "製品名2"],
    "dates": ["日付1", "日付2"],
    "other": ["その他の重要な固有名詞"]
}}"""

        response = self._call_llm(prompt)
        return self._parse_json_response(response)
