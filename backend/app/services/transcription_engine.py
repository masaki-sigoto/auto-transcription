import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptionSegment:
    """文字起こしセグメント"""
    start_time_ms: int
    end_time_ms: int
    text: str
    confidence: float | None = None
    speaker_id: str | None = None


@dataclass
class TranscriptionResult:
    """文字起こし結果"""
    segments: list[TranscriptionSegment]
    language: str
    duration_ms: int


class BaseTranscriptionEngine(ABC):
    """文字起こしエンジンの基底クラス"""

    @abstractmethod
    async def transcribe(self, audio_path: str, language: str = "ja") -> TranscriptionResult:
        """音声ファイルを文字起こし"""
        pass


class ReazonSpeechEngine(BaseTranscriptionEngine):
    """ReazonSpeechエンジン"""

    def __init__(self):
        self.model = None

    def _load_model(self):
        """モデルの遅延読み込み"""
        if self.model is None:
            try:
                from reazonspeech.nemo.asr import load_model, transcribe, audio_from_path
                self.model = load_model()
                self._transcribe_func = transcribe
                self._audio_from_path = audio_from_path
            except ImportError:
                raise RuntimeError("ReazonSpeech is not installed")

    async def transcribe(self, audio_path: str, language: str = "ja") -> TranscriptionResult:
        """ReazonSpeechで文字起こし"""
        self._load_model()

        audio = self._audio_from_path(audio_path)
        result = self._transcribe_func(self.model, audio)

        segments = []
        for seg in result.segments:
            segments.append(
                TranscriptionSegment(
                    start_time_ms=int(seg.start_seconds * 1000),
                    end_time_ms=int(seg.end_seconds * 1000),
                    text=seg.text,
                    confidence=getattr(seg, "confidence", None),
                )
            )

        duration_ms = int(result.segments[-1].end_seconds * 1000) if result.segments else 0

        return TranscriptionResult(
            segments=segments,
            language=language,
            duration_ms=duration_ms,
        )


class WhisperEngine(BaseTranscriptionEngine):
    """Whisperエンジン（faster-whisper使用）"""

    def __init__(self, model_size: str = "base"):
        # baseモデルは軽量で高速（large-v3は精度高いが重い）
        self.model_size = model_size
        self.model = None

    def _load_model(self):
        """モデルの遅延読み込み"""
        if self.model is None:
            try:
                from faster_whisper import WhisperModel
                # CPU使用、int8量子化で軽量化
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8"
                )
            except ImportError:
                raise RuntimeError("faster-whisper is not installed")

    async def transcribe(self, audio_path: str, language: str = "ja") -> TranscriptionResult:
        """Whisperで文字起こし"""
        self._load_model()

        segments_iter, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,  # 無音区間をスキップして高速化
        )

        segments = []
        last_end = 0
        for seg in segments_iter:
            segments.append(
                TranscriptionSegment(
                    start_time_ms=int(seg.start * 1000),
                    end_time_ms=int(seg.end * 1000),
                    text=seg.text.strip(),
                    confidence=seg.avg_logprob if hasattr(seg, 'avg_logprob') else None,
                )
            )
            last_end = seg.end

        duration_ms = int(last_end * 1000)

        return TranscriptionResult(
            segments=segments,
            language=language,
            duration_ms=duration_ms,
        )


class HybridEngine(BaseTranscriptionEngine):
    """ハイブリッドエンジン（ReazonSpeech + Whisperフォールバック）"""

    def __init__(self):
        self.reazon = ReazonSpeechEngine()
        self.whisper = WhisperEngine()

    async def transcribe(self, audio_path: str, language: str = "ja") -> TranscriptionResult:
        """ハイブリッド文字起こし"""
        # 日本語はReazonSpeechを優先
        if language == "ja":
            try:
                return await self.reazon.transcribe(audio_path, language)
            except Exception:
                # フォールバック
                return await self.whisper.transcribe(audio_path, language)
        else:
            # 日本語以外はWhisperを使用
            return await self.whisper.transcribe(audio_path, language)


def get_engine(engine_name: str) -> BaseTranscriptionEngine:
    """エンジン名からエンジンインスタンスを取得"""
    engines = {
        "reazon": ReazonSpeechEngine,
        "whisper": WhisperEngine,
        "hybrid": HybridEngine,
    }

    engine_class = engines.get(engine_name)
    if not engine_class:
        raise ValueError(f"Unknown engine: {engine_name}")

    return engine_class()
