"""翻訳サービス"""

from typing import Optional
from enum import Enum
import asyncio
import httpx
from pydantic import BaseModel


class SupportedLanguage(str, Enum):
    """サポートする言語"""

    JA = "ja"  # 日本語
    EN = "en"  # 英語
    ZH = "zh"  # 中国語
    KO = "ko"  # 韓国語
    ES = "es"  # スペイン語
    FR = "fr"  # フランス語
    DE = "de"  # ドイツ語
    PT = "pt"  # ポルトガル語
    RU = "ru"  # ロシア語
    AR = "ar"  # アラビア語


LANGUAGE_NAMES = {
    SupportedLanguage.JA: "日本語",
    SupportedLanguage.EN: "English",
    SupportedLanguage.ZH: "中文",
    SupportedLanguage.KO: "한국어",
    SupportedLanguage.ES: "Español",
    SupportedLanguage.FR: "Français",
    SupportedLanguage.DE: "Deutsch",
    SupportedLanguage.PT: "Português",
    SupportedLanguage.RU: "Русский",
    SupportedLanguage.AR: "العربية",
}


class TranslationResult(BaseModel):
    """翻訳結果"""

    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    confidence: float = 1.0


class TranslationService:
    """翻訳サービス"""

    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def translate(
        self,
        text: str,
        target_language: SupportedLanguage,
        source_language: Optional[SupportedLanguage] = None,
    ) -> TranslationResult:
        """テキストを翻訳"""
        target_name = LANGUAGE_NAMES.get(target_language, target_language.value)

        if source_language:
            source_name = LANGUAGE_NAMES.get(source_language, source_language.value)
            prompt = f"以下のテキストを{source_name}から{target_name}に翻訳してください。翻訳のみを出力し、説明は不要です。\n\n{text}"
        else:
            prompt = f"以下のテキストを{target_name}に翻訳してください。翻訳のみを出力し、説明は不要です。\n\n{text}"

        response = await self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "あなたは優秀な翻訳者です。自然で正確な翻訳を提供してください。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
        )

        response.raise_for_status()
        data = response.json()
        translated_text = data["choices"][0]["message"]["content"].strip()

        return TranslationResult(
            original_text=text,
            translated_text=translated_text,
            source_language=source_language.value if source_language else "auto",
            target_language=target_language.value,
        )

    async def translate_batch(
        self,
        texts: list[str],
        target_language: SupportedLanguage,
        source_language: Optional[SupportedLanguage] = None,
    ) -> list[TranslationResult]:
        """複数テキストを並列翻訳"""
        tasks = [
            self.translate(text, target_language, source_language) for text in texts
        ]
        return await asyncio.gather(*tasks)

    async def detect_language(self, text: str) -> SupportedLanguage:
        """言語を検出"""
        response = await self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "テキストの言語を検出し、言語コード（ja, en, zh, ko, es, fr, de, pt, ru, ar）のみを返してください。",
                    },
                    {"role": "user", "content": text[:500]},
                ],
                "temperature": 0,
            },
        )

        response.raise_for_status()
        data = response.json()
        lang_code = data["choices"][0]["message"]["content"].strip().lower()

        try:
            return SupportedLanguage(lang_code)
        except ValueError:
            return SupportedLanguage.EN  # デフォルト

    async def close(self):
        await self.client.aclose()


class RealTimeTranslator:
    """リアルタイム翻訳器"""

    def __init__(self, translation_service: TranslationService):
        self.service = translation_service
        self._buffer: list[str] = []
        self._buffer_size = 3

    async def process_segment(
        self,
        text: str,
        target_language: SupportedLanguage,
        source_language: Optional[SupportedLanguage] = None,
    ) -> Optional[TranslationResult]:
        """セグメントを処理してバッファリング翻訳"""
        self._buffer.append(text)

        # バッファが溜まったら翻訳
        if len(self._buffer) >= self._buffer_size:
            combined_text = " ".join(self._buffer)
            self._buffer = []
            return await self.service.translate(
                combined_text, target_language, source_language
            )

        return None

    async def flush(
        self,
        target_language: SupportedLanguage,
        source_language: Optional[SupportedLanguage] = None,
    ) -> Optional[TranslationResult]:
        """バッファをフラッシュして残りを翻訳"""
        if self._buffer:
            combined_text = " ".join(self._buffer)
            self._buffer = []
            return await self.service.translate(
                combined_text, target_language, source_language
            )
        return None


# === 拡張機能 ===

from dataclasses import dataclass, field
from typing import Dict, List, Any, AsyncGenerator
import uuid


@dataclass
class GlossaryEntry:
    """用語集エントリ"""
    id: str
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    context: Optional[str] = None


@dataclass
class TranslationMemoryEntry:
    """翻訳メモリエントリ"""
    id: str
    source_text: str
    translated_text: str
    source_language: str
    target_language: str
    similarity_score: float = 1.0
    usage_count: int = 0


class GlossaryManager:
    """用語集管理"""

    def __init__(self):
        self._glossaries: Dict[str, List[GlossaryEntry]] = {}

    async def create_glossary(self, name: str, tenant_id: str) -> str:
        """用語集を作成"""
        glossary_id = str(uuid.uuid4())
        self._glossaries[glossary_id] = []
        return glossary_id

    async def add_entry(
        self,
        glossary_id: str,
        source_term: str,
        target_term: str,
        source_language: str,
        target_language: str,
        context: Optional[str] = None,
    ) -> GlossaryEntry:
        """エントリを追加"""
        if glossary_id not in self._glossaries:
            self._glossaries[glossary_id] = []

        entry = GlossaryEntry(
            id=str(uuid.uuid4()),
            source_term=source_term,
            target_term=target_term,
            source_language=source_language,
            target_language=target_language,
            context=context,
        )
        self._glossaries[glossary_id].append(entry)
        return entry

    async def get_entries(
        self,
        glossary_id: str,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> List[GlossaryEntry]:
        """エントリを取得"""
        entries = self._glossaries.get(glossary_id, [])
        if source_language:
            entries = [e for e in entries if e.source_language == source_language]
        if target_language:
            entries = [e for e in entries if e.target_language == target_language]
        return entries

    async def import_glossary(
        self,
        glossary_id: str,
        entries: List[Dict[str, Any]],
    ) -> int:
        """用語集をインポート"""
        if glossary_id not in self._glossaries:
            self._glossaries[glossary_id] = []

        count = 0
        for data in entries:
            entry = GlossaryEntry(
                id=str(uuid.uuid4()),
                source_term=data["source_term"],
                target_term=data["target_term"],
                source_language=data["source_language"],
                target_language=data["target_language"],
                context=data.get("context"),
            )
            self._glossaries[glossary_id].append(entry)
            count += 1
        return count

    async def delete_glossary(self, glossary_id: str) -> bool:
        """用語集を削除"""
        if glossary_id in self._glossaries:
            del self._glossaries[glossary_id]
            return True
        return False


class TranslationMemory:
    """翻訳メモリ"""

    def __init__(self):
        self._memory: Dict[str, List[TranslationMemoryEntry]] = {}

    async def store(
        self,
        tenant_id: str,
        source_text: str,
        translated_text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationMemoryEntry:
        """翻訳を保存"""
        if tenant_id not in self._memory:
            self._memory[tenant_id] = []

        entry = TranslationMemoryEntry(
            id=str(uuid.uuid4()),
            source_text=source_text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language,
        )
        self._memory[tenant_id].append(entry)
        return entry

    async def search(
        self,
        tenant_id: str,
        text: str,
        source_language: str,
        target_language: str,
        min_similarity: float = 0.8,
    ) -> List[TranslationMemoryEntry]:
        """類似翻訳を検索"""
        entries = self._memory.get(tenant_id, [])
        entries = [
            e for e in entries
            if e.source_language == source_language and e.target_language == target_language
        ]

        results = []
        for entry in entries:
            similarity = self._calculate_similarity(text, entry.source_text)
            if similarity >= min_similarity:
                entry.similarity_score = similarity
                results.append(entry)

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:5]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """類似度を計算"""
        if text1 == text2:
            return 1.0
        words1, words2 = set(text1.split()), set(text2.split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)

    async def get_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """統計を取得"""
        entries = self._memory.get(tenant_id, [])
        return {
            "total_entries": len(entries),
            "language_pairs": len(set((e.source_language, e.target_language) for e in entries)),
        }


class SimultaneousInterpreter:
    """同時通訳サービス"""

    def __init__(self, translation_service: TranslationService):
        self.service = translation_service
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def create_session(
        self,
        source_language: SupportedLanguage,
        target_languages: List[SupportedLanguage],
    ) -> str:
        """セッションを作成"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "source_language": source_language,
            "target_languages": target_languages,
            "is_active": True,
            "segments_count": 0,
        }
        return session_id

    async def translate_segment(
        self,
        session_id: str,
        text: str,
    ) -> Dict[str, TranslationResult]:
        """セグメントを多言語翻訳"""
        session = self._sessions.get(session_id)
        if not session or not session["is_active"]:
            raise ValueError("Session not found or inactive")

        results = {}
        for target_lang in session["target_languages"]:
            result = await self.service.translate(
                text,
                target_lang,
                session["source_language"],
            )
            results[target_lang.value] = result

        session["segments_count"] += 1
        return results

    async def end_session(self, session_id: str) -> bool:
        """セッションを終了"""
        if session_id in self._sessions:
            self._sessions[session_id]["is_active"] = False
            return True
        return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """セッション情報を取得"""
        return self._sessions.get(session_id)


class SubtitleGenerator:
    """多言語字幕生成"""

    def __init__(self, translation_service: TranslationService):
        self.service = translation_service

    async def generate_subtitles(
        self,
        segments: List[Dict[str, Any]],
        target_languages: List[SupportedLanguage],
        source_language: SupportedLanguage,
        format: str = "vtt",
    ) -> Dict[str, str]:
        """多言語字幕を生成"""
        subtitles = {}

        for target_lang in target_languages:
            if format == "vtt":
                content = await self._generate_vtt(segments, source_language, target_lang)
            elif format == "srt":
                content = await self._generate_srt(segments, source_language, target_lang)
            else:
                content = await self._generate_vtt(segments, source_language, target_lang)

            subtitles[target_lang.value] = content

        return subtitles

    async def _generate_vtt(
        self,
        segments: List[Dict[str, Any]],
        source_language: SupportedLanguage,
        target_language: SupportedLanguage,
    ) -> str:
        """WebVTT形式を生成"""
        lines = ["WEBVTT", ""]

        for seg in segments:
            text = seg.get("text", "")
            if source_language != target_language:
                result = await self.service.translate(text, target_language, source_language)
                text = result.translated_text

            start = self._ms_to_vtt_time(seg.get("start_time_ms", 0))
            end = self._ms_to_vtt_time(seg.get("end_time_ms", 0))

            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    async def _generate_srt(
        self,
        segments: List[Dict[str, Any]],
        source_language: SupportedLanguage,
        target_language: SupportedLanguage,
    ) -> str:
        """SRT形式を生成"""
        lines = []

        for i, seg in enumerate(segments, 1):
            text = seg.get("text", "")
            if source_language != target_language:
                result = await self.service.translate(text, target_language, source_language)
                text = result.translated_text

            start = self._ms_to_srt_time(seg.get("start_time_ms", 0))
            end = self._ms_to_srt_time(seg.get("end_time_ms", 0))

            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def _ms_to_vtt_time(self, ms: int) -> str:
        h, m, s = ms // 3600000, (ms % 3600000) // 60000, (ms % 60000) // 1000
        return f"{h:02d}:{m:02d}:{s:02d}.{ms % 1000:03d}"

    def _ms_to_srt_time(self, ms: int) -> str:
        h, m, s = ms // 3600000, (ms % 3600000) // 60000, (ms % 60000) // 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms % 1000:03d}"


# グローバルインスタンス
glossary_manager = GlossaryManager()
translation_memory = TranslationMemory()
