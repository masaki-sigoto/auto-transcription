"""多言語対応サービス"""

from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.transcription import Transcription, TranscriptionSegment
from app.services.translation_service import (
    TranslationService,
    SupportedLanguage,
    TranslationResult,
)


class MultilingualTranscription:
    """多言語文字起こし結果"""

    def __init__(
        self,
        transcription_id: UUID,
        original_language: str,
        translations: dict[str, list[dict]],
    ):
        self.transcription_id = transcription_id
        self.original_language = original_language
        self.translations = translations


class MultilingualService:
    """多言語対応サービス"""

    def __init__(self, db: AsyncSession, translation_service: TranslationService):
        self.db = db
        self.translation_service = translation_service

    async def translate_transcription(
        self,
        transcription_id: UUID,
        target_languages: list[SupportedLanguage],
    ) -> MultilingualTranscription:
        """文字起こし全体を複数言語に翻訳"""
        # 文字起こしを取得
        result = await self.db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise ValueError("Transcription not found")

        # セグメントを取得
        segments_result = await self.db.execute(
            select(TranscriptionSegment)
            .where(TranscriptionSegment.transcription_id == transcription_id)
            .order_by(TranscriptionSegment.start_time_ms)
        )
        segments = segments_result.scalars().all()

        # 各言語に翻訳
        translations: dict[str, list[dict]] = {}

        for target_lang in target_languages:
            translated_segments = []

            for segment in segments:
                translation = await self.translation_service.translate(
                    segment.text,
                    target_lang,
                    SupportedLanguage(transcription.language)
                    if transcription.language
                    else None,
                )

                translated_segments.append(
                    {
                        "segment_id": str(segment.id),
                        "start_time_ms": segment.start_time_ms,
                        "end_time_ms": segment.end_time_ms,
                        "original_text": segment.text,
                        "translated_text": translation.translated_text,
                        "speaker_id": str(segment.speaker_id)
                        if segment.speaker_id
                        else None,
                    }
                )

            translations[target_lang.value] = translated_segments

        return MultilingualTranscription(
            transcription_id=transcription_id,
            original_language=transcription.language or "ja",
            translations=translations,
        )

    async def get_subtitle_in_language(
        self,
        transcription_id: UUID,
        target_language: SupportedLanguage,
        format: str = "srt",
    ) -> str:
        """特定言語の字幕を生成"""
        multilingual = await self.translate_transcription(
            transcription_id, [target_language]
        )

        segments = multilingual.translations.get(target_language.value, [])

        if format == "srt":
            return self._generate_srt(segments)
        elif format == "vtt":
            return self._generate_vtt(segments)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_srt(self, segments: list[dict]) -> str:
        """SRT形式を生成"""
        lines = []
        for i, segment in enumerate(segments, 1):
            start = self._ms_to_srt_time(segment["start_time_ms"])
            end = self._ms_to_srt_time(segment["end_time_ms"])
            text = segment["translated_text"]

            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def _generate_vtt(self, segments: list[dict]) -> str:
        """VTT形式を生成"""
        lines = ["WEBVTT", ""]
        for segment in segments:
            start = self._ms_to_vtt_time(segment["start_time_ms"])
            end = self._ms_to_vtt_time(segment["end_time_ms"])
            text = segment["translated_text"]

            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def _ms_to_srt_time(self, ms: int) -> str:
        """ミリ秒をSRT時間形式に変換"""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _ms_to_vtt_time(self, ms: int) -> str:
        """ミリ秒をVTT時間形式に変換"""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


class LanguageDetectionService:
    """言語検出サービス"""

    def __init__(self, translation_service: TranslationService):
        self.translation_service = translation_service

    async def detect_from_audio(self, audio_path: str) -> SupportedLanguage:
        """
        音声ファイルから言語を検出
        Whisperの言語検出を使用
        """
        # Whisperの言語検出機能を使用
        # 実装はWhisperサービスに委譲
        return SupportedLanguage.JA  # デフォルト

    async def detect_from_text(self, text: str) -> SupportedLanguage:
        """テキストから言語を検出"""
        return await self.translation_service.detect_language(text)

    async def suggest_languages(
        self, source_language: SupportedLanguage
    ) -> list[SupportedLanguage]:
        """ソース言語に基づいておすすめの翻訳言語を提案"""
        # よく使われる翻訳ペアを定義
        recommendations = {
            SupportedLanguage.JA: [
                SupportedLanguage.EN,
                SupportedLanguage.ZH,
                SupportedLanguage.KO,
            ],
            SupportedLanguage.EN: [
                SupportedLanguage.JA,
                SupportedLanguage.ZH,
                SupportedLanguage.ES,
            ],
            SupportedLanguage.ZH: [
                SupportedLanguage.EN,
                SupportedLanguage.JA,
                SupportedLanguage.KO,
            ],
            SupportedLanguage.KO: [
                SupportedLanguage.JA,
                SupportedLanguage.EN,
                SupportedLanguage.ZH,
            ],
        }

        return recommendations.get(
            source_language,
            [SupportedLanguage.EN, SupportedLanguage.JA, SupportedLanguage.ZH],
        )
