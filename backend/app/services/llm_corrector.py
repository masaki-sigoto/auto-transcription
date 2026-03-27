import json
from anthropic import Anthropic

from app.core.config import get_settings
from app.services.transcription_engine import TranscriptionSegment


class LLMCorrector:
    """LLMによる文字起こし補正"""

    CORRECTION_PROMPT = """この文字起こしテキストをチェックして、以下の修正を行ってください：

1. 表記が不自然な箇所を修正
2. 句読点を適切に挿入
3. フィラーワード（えー、あのー、まあ等）を除去
4. 専門用語・固有名詞は文脈に合わせた適切な表記に
5. タイムスタンプは絶対に変更しない

入力はJSON形式です。同じJSON形式で出力してください。
text フィールドのみ修正し、他のフィールドは変更しないでください。

---
入力:
{segments_json}
---

出力（JSON形式のみ、説明不要）:"""

    SUMMARY_PROMPT = """以下の文字起こしテキストを要約してください。

要件:
- 主要な議題・トピックを箇条書きで抽出
- 決定事項があれば明記
- アクションアイテムがあれば抽出
- 全体の要約を3-5文で記述

文字起こしテキスト:
{text}

---
以下のJSON形式で出力してください:
{{
    "summary": "全体の要約文",
    "topics": ["トピック1", "トピック2"],
    "decisions": ["決定事項1"],
    "action_items": ["アクションアイテム1"]
}}"""

    def __init__(self):
        settings = get_settings()
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    async def correct_segments(
        self, segments: list[TranscriptionSegment], batch_size: int = 20
    ) -> list[TranscriptionSegment]:
        """セグメントのテキストを補正"""
        corrected_segments = []

        # バッチ処理
        for i in range(0, len(segments), batch_size):
            batch = segments[i : i + batch_size]
            corrected_batch = await self._correct_batch(batch)
            corrected_segments.extend(corrected_batch)

        return corrected_segments

    async def _correct_batch(
        self, segments: list[TranscriptionSegment]
    ) -> list[TranscriptionSegment]:
        """バッチ単位で補正"""
        segments_data = [
            {
                "start_time_ms": seg.start_time_ms,
                "end_time_ms": seg.end_time_ms,
                "text": seg.text,
            }
            for seg in segments
        ]

        prompt = self.CORRECTION_PROMPT.format(
            segments_json=json.dumps(segments_data, ensure_ascii=False, indent=2)
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            response_text = response.content[0].text
            # JSONを抽出（コードブロックがある場合は除去）
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            corrected_data = json.loads(response_text.strip())

            # 補正されたセグメントを作成
            corrected_segments = []
            for i, seg in enumerate(segments):
                corrected_text = corrected_data[i]["text"] if i < len(corrected_data) else seg.text
                corrected_segments.append(
                    TranscriptionSegment(
                        start_time_ms=seg.start_time_ms,
                        end_time_ms=seg.end_time_ms,
                        text=corrected_text,
                        confidence=seg.confidence,
                        speaker_id=seg.speaker_id,
                    )
                )
            return corrected_segments

        except (json.JSONDecodeError, KeyError, IndexError):
            # パースエラーの場合は元のセグメントを返す
            return segments

    async def generate_summary(self, segments: list[TranscriptionSegment]) -> dict:
        """文字起こしの要約を生成"""
        full_text = "\n".join(
            [f"[{seg.start_time_ms // 1000}s] {seg.text}" for seg in segments]
        )

        prompt = self.SUMMARY_PROMPT.format(text=full_text)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            response_text = response.content[0].text
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text.strip())

        except (json.JSONDecodeError, KeyError):
            return {
                "summary": "",
                "topics": [],
                "decisions": [],
                "action_items": [],
            }
