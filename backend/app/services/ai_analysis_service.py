"""AI分析サービス"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from pydantic import BaseModel

from app.models.transcription import Transcription, TranscriptionSegment
from app.core.config import get_settings

settings = get_settings()


class MeetingMinutes(BaseModel):
    """議事録"""
    title: str
    date: str
    participants: list[str]
    summary: str
    key_points: list[str]
    action_items: list[dict]
    decisions: list[str]
    next_steps: list[str]


class SentimentResult(BaseModel):
    """感情分析結果"""
    overall_sentiment: str  # positive, negative, neutral
    sentiment_score: float  # -1.0 to 1.0
    segments: list[dict]
    speaker_sentiments: dict[str, dict]


class KeywordResult(BaseModel):
    """キーワード抽出結果"""
    keywords: list[dict]  # [{word, frequency, importance}]
    topics: list[dict]  # [{topic, keywords, segments}]
    entities: list[dict]  # [{name, type, count}]


class QAResult(BaseModel):
    """質問応答結果"""
    question: str
    answer: str
    confidence: float
    relevant_segments: list[dict]


class AIAnalysisService:
    """AI分析サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = httpx.AsyncClient(timeout=60.0)
        self.openai_url = "https://api.openai.com/v1/chat/completions"

    async def _call_openai(
        self,
        messages: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.3,
        response_format: Optional[dict] = None,
    ) -> str:
        """OpenAI APIを呼び出し"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if response_format:
            payload["response_format"] = response_format

        response = await self.client.post(
            self.openai_url,
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _get_transcription_text(self, transcription_id: UUID) -> tuple[str, list]:
        """文字起こしテキストを取得"""
        result = await self.db.execute(
            select(TranscriptionSegment)
            .where(TranscriptionSegment.transcription_id == transcription_id)
            .order_by(TranscriptionSegment.start_time_ms)
        )
        segments = result.scalars().all()

        full_text = "\n".join([s.text for s in segments])
        return full_text, segments

    async def generate_meeting_minutes(
        self,
        transcription_id: UUID,
        include_action_items: bool = True,
    ) -> MeetingMinutes:
        """議事録を自動生成"""
        # 文字起こしを取得
        result = await self.db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise ValueError("Transcription not found")

        full_text, segments = await self._get_transcription_text(transcription_id)

        # プロンプトを構築
        prompt = f"""以下の会議の文字起こしから、構造化された議事録を作成してください。

文字起こし:
{full_text[:15000]}

以下の形式でJSONを返してください:
{{
    "title": "会議のタイトル",
    "summary": "会議の要約（3-5文）",
    "key_points": ["重要なポイント1", "重要なポイント2", ...],
    "action_items": [
        {{"task": "タスク内容", "assignee": "担当者（わかれば）", "deadline": "期限（わかれば）"}}
    ],
    "decisions": ["決定事項1", "決定事項2", ...],
    "next_steps": ["次のステップ1", "次のステップ2", ...]
}}"""

        response = await self._call_openai(
            messages=[
                {"role": "system", "content": "あなたは優秀な議事録作成アシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        import json
        data = json.loads(response)

        # 参加者を取得
        participants = []
        for segment in segments:
            if segment.speaker_id and segment.speaker_id not in participants:
                participants.append(str(segment.speaker_id))

        return MeetingMinutes(
            title=data.get("title", transcription.title),
            date=transcription.created_at.strftime("%Y-%m-%d"),
            participants=participants,
            summary=data.get("summary", ""),
            key_points=data.get("key_points", []),
            action_items=data.get("action_items", []),
            decisions=data.get("decisions", []),
            next_steps=data.get("next_steps", []),
        )

    async def analyze_sentiment(
        self,
        transcription_id: UUID,
    ) -> SentimentResult:
        """感情分析を実行"""
        full_text, segments = await self._get_transcription_text(transcription_id)

        # 全体の感情分析
        overall_prompt = f"""以下のテキストの感情を分析してください。

テキスト:
{full_text[:10000]}

以下の形式でJSONを返してください:
{{
    "overall_sentiment": "positive/negative/neutral",
    "sentiment_score": 0.5,  // -1.0 to 1.0
    "emotions": {{"joy": 0.3, "anger": 0.1, "sadness": 0.1, "surprise": 0.2, "fear": 0.1, "neutral": 0.2}}
}}"""

        overall_response = await self._call_openai(
            messages=[
                {"role": "system", "content": "あなたは感情分析の専門家です。"},
                {"role": "user", "content": overall_prompt},
            ],
            response_format={"type": "json_object"},
        )

        import json
        overall_data = json.loads(overall_response)

        # セグメントごとの感情分析（サンプリング）
        segment_sentiments = []
        sample_segments = segments[::max(1, len(segments) // 20)]  # 最大20セグメント

        for segment in sample_segments:
            segment_prompt = f"""以下のテキストの感情を分析してください:
"{segment.text}"

JSONで返してください: {{"sentiment": "positive/negative/neutral", "score": 0.5}}"""

            try:
                seg_response = await self._call_openai(
                    messages=[{"role": "user", "content": segment_prompt}],
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                )
                seg_data = json.loads(seg_response)

                segment_sentiments.append({
                    "segment_id": str(segment.id),
                    "start_time_ms": segment.start_time_ms,
                    "text": segment.text[:100],
                    "sentiment": seg_data.get("sentiment", "neutral"),
                    "score": seg_data.get("score", 0),
                })
            except Exception:
                continue

        # 話者ごとの感情集計
        speaker_sentiments = {}
        for seg in segment_sentiments:
            # 簡略化のため、話者ごとの集計は省略

        return SentimentResult(
            overall_sentiment=overall_data.get("overall_sentiment", "neutral"),
            sentiment_score=overall_data.get("sentiment_score", 0),
            segments=segment_sentiments,
            speaker_sentiments=speaker_sentiments,
        )

    async def extract_keywords(
        self,
        transcription_id: UUID,
        max_keywords: int = 20,
    ) -> KeywordResult:
        """キーワードを抽出"""
        full_text, segments = await self._get_transcription_text(transcription_id)

        prompt = f"""以下のテキストから重要なキーワード、トピック、固有表現を抽出してください。

テキスト:
{full_text[:15000]}

以下の形式でJSONを返してください:
{{
    "keywords": [
        {{"word": "キーワード", "frequency": 5, "importance": 0.9}}
    ],
    "topics": [
        {{"topic": "トピック名", "keywords": ["関連キーワード1", "関連キーワード2"]}}
    ],
    "entities": [
        {{"name": "固有表現", "type": "person/organization/location/product/date", "count": 3}}
    ]
}}"""

        response = await self._call_openai(
            messages=[
                {"role": "system", "content": "あなたは自然言語処理の専門家です。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        import json
        data = json.loads(response)

        # キーワードを上位N件に制限
        keywords = sorted(
            data.get("keywords", []),
            key=lambda x: x.get("importance", 0),
            reverse=True,
        )[:max_keywords]

        return KeywordResult(
            keywords=keywords,
            topics=data.get("topics", []),
            entities=data.get("entities", []),
        )

    async def answer_question(
        self,
        transcription_id: UUID,
        question: str,
    ) -> QAResult:
        """文字起こし内容に関する質問に回答"""
        full_text, segments = await self._get_transcription_text(transcription_id)

        prompt = f"""以下の文字起こし内容に基づいて、質問に回答してください。

文字起こし:
{full_text[:15000]}

質問: {question}

以下の形式でJSONを返してください:
{{
    "answer": "回答テキスト",
    "confidence": 0.85,
    "relevant_segments": [
        {{"text": "関連するセグメントのテキスト", "start_time_ms": 12000}}
    ]
}}

文字起こしに含まれない情報については「この情報は文字起こしに含まれていません」と回答してください。"""

        response = await self._call_openai(
            messages=[
                {"role": "system", "content": "あなたは質問応答の専門家です。文字起こしの内容に基づいて正確に回答してください。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        import json
        data = json.loads(response)

        return QAResult(
            question=question,
            answer=data.get("answer", ""),
            confidence=data.get("confidence", 0),
            relevant_segments=data.get("relevant_segments", []),
        )

    async def generate_summary(
        self,
        transcription_id: UUID,
        style: str = "concise",  # concise, detailed, bullet_points
    ) -> str:
        """要約を生成"""
        full_text, _ = await self._get_transcription_text(transcription_id)

        style_instructions = {
            "concise": "3-5文の簡潔な要約を作成してください。",
            "detailed": "詳細な要約を段落形式で作成してください。重要なポイントをすべて含めてください。",
            "bullet_points": "箇条書き形式で要約を作成してください。",
        }

        prompt = f"""以下の文字起こしを要約してください。

{style_instructions.get(style, style_instructions["concise"])}

文字起こし:
{full_text[:15000]}"""

        response = await self._call_openai(
            messages=[
                {"role": "system", "content": "あなたは要約の専門家です。"},
                {"role": "user", "content": prompt},
            ],
        )

        return response

    async def close(self):
        await self.client.aclose()
