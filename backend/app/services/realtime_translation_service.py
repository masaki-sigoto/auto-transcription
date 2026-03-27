"""リアルタイム翻訳サービス"""

import asyncio
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum

from app.services.translation_service import (
    TranslationService,
    SupportedLanguage,
    TranslationResult,
)


class TranslationMode(str, Enum):
    """翻訳モード"""

    INSTANT = "instant"  # 即時翻訳（セグメントごと）
    BUFFERED = "buffered"  # バッファリング翻訳（複数セグメント結合）
    SMART = "smart"  # スマート翻訳（文の区切りを検出）


@dataclass
class RealtimeTranslationConfig:
    """リアルタイム翻訳設定"""

    mode: TranslationMode = TranslationMode.SMART
    buffer_size: int = 3
    buffer_timeout_ms: int = 2000
    target_languages: list[SupportedLanguage] = None

    def __post_init__(self):
        if self.target_languages is None:
            self.target_languages = [SupportedLanguage.EN]


class RealtimeTranslationSession:
    """リアルタイム翻訳セッション"""

    def __init__(
        self,
        translation_service: TranslationService,
        config: RealtimeTranslationConfig,
        on_translation: Optional[Callable[[dict], None]] = None,
    ):
        self.service = translation_service
        self.config = config
        self.on_translation = on_translation

        self._buffer: list[str] = []
        self._buffer_task: Optional[asyncio.Task] = None
        self._source_language: Optional[SupportedLanguage] = None
        self._is_running = False

    async def start(self, source_language: Optional[SupportedLanguage] = None):
        """セッションを開始"""
        self._source_language = source_language
        self._is_running = True
        self._buffer = []

    async def stop(self):
        """セッションを停止"""
        self._is_running = False

        # バッファをフラッシュ
        if self._buffer:
            await self._flush_buffer()

        if self._buffer_task:
            self._buffer_task.cancel()

    async def process_segment(self, text: str) -> dict[str, TranslationResult]:
        """セグメントを処理"""
        if not self._is_running:
            return {}

        if self.config.mode == TranslationMode.INSTANT:
            return await self._translate_instant(text)
        elif self.config.mode == TranslationMode.BUFFERED:
            return await self._translate_buffered(text)
        else:  # SMART
            return await self._translate_smart(text)

    async def _translate_instant(self, text: str) -> dict[str, TranslationResult]:
        """即時翻訳"""
        results = {}
        for target_lang in self.config.target_languages:
            result = await self.service.translate(
                text, target_lang, self._source_language
            )
            results[target_lang.value] = result

            if self.on_translation:
                self.on_translation(
                    {
                        "type": "translation",
                        "language": target_lang.value,
                        "original": text,
                        "translated": result.translated_text,
                    }
                )

        return results

    async def _translate_buffered(self, text: str) -> dict[str, TranslationResult]:
        """バッファリング翻訳"""
        self._buffer.append(text)

        if len(self._buffer) >= self.config.buffer_size:
            return await self._flush_buffer()

        # タイムアウト設定
        if self._buffer_task:
            self._buffer_task.cancel()

        self._buffer_task = asyncio.create_task(self._buffer_timeout())
        return {}

    async def _translate_smart(self, text: str) -> dict[str, TranslationResult]:
        """スマート翻訳（文の区切りを検出）"""
        self._buffer.append(text)

        # 文の終わりを検出
        if self._is_sentence_end(text):
            return await self._flush_buffer()

        # バッファサイズ上限
        if len(self._buffer) >= self.config.buffer_size:
            return await self._flush_buffer()

        return {}

    def _is_sentence_end(self, text: str) -> bool:
        """文の終わりかどうかを判定"""
        sentence_enders = ["。", ".", "！", "!", "？", "?", "…", "...", "\n"]
        return any(text.strip().endswith(e) for e in sentence_enders)

    async def _buffer_timeout(self):
        """バッファタイムアウト"""
        await asyncio.sleep(self.config.buffer_timeout_ms / 1000)
        if self._buffer:
            await self._flush_buffer()

    async def _flush_buffer(self) -> dict[str, TranslationResult]:
        """バッファをフラッシュして翻訳"""
        if not self._buffer:
            return {}

        combined_text = " ".join(self._buffer)
        self._buffer = []

        results = {}
        for target_lang in self.config.target_languages:
            result = await self.service.translate(
                combined_text, target_lang, self._source_language
            )
            results[target_lang.value] = result

            if self.on_translation:
                self.on_translation(
                    {
                        "type": "translation",
                        "language": target_lang.value,
                        "original": combined_text,
                        "translated": result.translated_text,
                    }
                )

        return results


class RealtimeTranslationManager:
    """リアルタイム翻訳マネージャー"""

    def __init__(self, translation_service: TranslationService):
        self.service = translation_service
        self._sessions: dict[str, RealtimeTranslationSession] = {}

    async def create_session(
        self,
        session_id: str,
        config: RealtimeTranslationConfig,
        on_translation: Optional[Callable[[dict], None]] = None,
    ) -> RealtimeTranslationSession:
        """新しいセッションを作成"""
        session = RealtimeTranslationSession(self.service, config, on_translation)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[RealtimeTranslationSession]:
        """セッションを取得"""
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        """セッションを閉じる"""
        session = self._sessions.pop(session_id, None)
        if session:
            await session.stop()

    async def close_all(self):
        """すべてのセッションを閉じる"""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
