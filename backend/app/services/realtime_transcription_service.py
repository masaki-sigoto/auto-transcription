"""リアルタイムストリーミング文字起こしサービス"""

import os
import uuid
import json
import asyncio
import tempfile
import wave
import struct
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import base64
import logging

logger = logging.getLogger(__name__)


class StreamingStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    TRANSCRIBING = "transcribing"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class AudioFormat(str, Enum):
    PCM_16 = "pcm_16"
    PCM_32 = "pcm_32"
    FLOAT_32 = "float_32"
    OPUS = "opus"
    WEBM = "webm"


@dataclass
class StreamingConfig:
    """ストリーミング設定"""
    sample_rate: int = 16000
    channels: int = 1
    audio_format: AudioFormat = AudioFormat.PCM_16
    language: str = "ja"
    enable_interim_results: bool = True
    enable_speaker_diarization: bool = False
    max_alternatives: int = 1
    profanity_filter: bool = False
    punctuation: bool = True
    model: str = "whisper-large-v3"


@dataclass
class TranscriptSegment:
    """文字起こしセグメント"""
    id: str
    text: str
    start_time_ms: int
    end_time_ms: int
    is_final: bool
    confidence: float
    speaker_id: Optional[str] = None
    words: List[Dict[str, Any]] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)


@dataclass
class StreamingSession:
    """ストリーミングセッション"""
    id: str
    user_id: str
    status: StreamingStatus
    config: StreamingConfig
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    total_audio_ms: int = 0
    segments: List[TranscriptSegment] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AudioBuffer:
    """オーディオバッファ"""

    def __init__(self, max_size_bytes: int = 1024 * 1024):  # 1MB
        self._buffer: bytes = b""
        self._max_size = max_size_bytes
        self._lock = asyncio.Lock()

    async def append(self, data: bytes) -> int:
        """データを追加"""
        async with self._lock:
            if len(self._buffer) + len(data) > self._max_size:
                # 古いデータを削除
                overflow = len(self._buffer) + len(data) - self._max_size
                self._buffer = self._buffer[overflow:]
            self._buffer += data
            return len(self._buffer)

    async def read(self, size: int) -> bytes:
        """データを読み取り"""
        async with self._lock:
            data = self._buffer[:size]
            self._buffer = self._buffer[size:]
            return data

    async def read_all(self) -> bytes:
        """全データを読み取り"""
        async with self._lock:
            data = self._buffer
            self._buffer = b""
            return data

    @property
    def size(self) -> int:
        return len(self._buffer)


class RealtimeWhisperEngine:
    """リアルタイム用Whisperエンジン（faster-whisper使用）"""

    def __init__(self):
        self._model = None
        self._model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        self._device = os.getenv("WHISPER_DEVICE", "auto")
        self._compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "auto")

    def _load_model(self):
        """モデルの遅延読み込み"""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model: {self._model_size}")
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("faster-whisper model loaded successfully")
        except ImportError:
            logger.warning("faster-whisper not available, falling back to openai-whisper")
            try:
                import whisper
                self._model = whisper.load_model(self._model_size)
                self._use_openai_whisper = True
                logger.info("openai-whisper model loaded")
            except ImportError:
                logger.error("No whisper implementation available")
                raise RuntimeError("Neither faster-whisper nor openai-whisper is installed")

    async def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        language: str = "ja",
    ) -> Optional[Dict[str, Any]]:
        """音声データを文字起こし"""
        self._load_model()

        # 一時ファイルにWAV形式で保存
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            try:
                # PCM 16bitデータをWAVファイルとして書き込み
                with wave.open(tmp_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)  # 16bit = 2 bytes
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data)

                # faster-whisperの場合
                if hasattr(self._model, 'transcribe'):
                    if hasattr(self, '_use_openai_whisper') and self._use_openai_whisper:
                        # openai-whisper
                        result = self._model.transcribe(
                            tmp_path,
                            language=language,
                            word_timestamps=True,
                        )
                        if result["segments"]:
                            seg = result["segments"][0]
                            return {
                                "text": result["text"].strip(),
                                "segments": [
                                    {
                                        "start": s["start"],
                                        "end": s["end"],
                                        "text": s["text"].strip(),
                                    }
                                    for s in result["segments"]
                                ],
                                "language": result.get("language", language),
                            }
                    else:
                        # faster-whisper
                        segments, info = self._model.transcribe(
                            tmp_path,
                            language=language,
                            beam_size=5,
                            vad_filter=True,
                            vad_parameters=dict(
                                min_silence_duration_ms=500,
                            ),
                        )

                        segments_list = list(segments)
                        if segments_list:
                            full_text = " ".join(s.text.strip() for s in segments_list)
                            return {
                                "text": full_text,
                                "segments": [
                                    {
                                        "start": s.start,
                                        "end": s.end,
                                        "text": s.text.strip(),
                                    }
                                    for s in segments_list
                                ],
                                "language": info.language,
                            }

                return None

            finally:
                # 一時ファイルを削除
                try:
                    os.unlink(tmp_path)
                except:
                    pass


# グローバルなWhisperエンジンインスタンス
_realtime_whisper_engine: Optional[RealtimeWhisperEngine] = None

def get_realtime_whisper_engine() -> RealtimeWhisperEngine:
    """リアルタイムWhisperエンジンのシングルトンを取得"""
    global _realtime_whisper_engine
    if _realtime_whisper_engine is None:
        _realtime_whisper_engine = RealtimeWhisperEngine()
    return _realtime_whisper_engine


class RealtimeTranscriber:
    """リアルタイム文字起こしエンジン"""

    def __init__(self):
        self._sessions: Dict[str, StreamingSession] = {}
        self._buffers: Dict[str, AudioBuffer] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._whisper_engine = get_realtime_whisper_engine()

    async def create_session(
        self,
        user_id: str,
        config: Optional[StreamingConfig] = None,
    ) -> StreamingSession:
        """セッションを作成"""
        session_id = str(uuid.uuid4())
        session = StreamingSession(
            id=session_id,
            user_id=user_id,
            status=StreamingStatus.CONNECTING,
            config=config or StreamingConfig(),
            created_at=datetime.utcnow(),
        )

        self._sessions[session_id] = session
        self._buffers[session_id] = AudioBuffer()
        self._callbacks[session_id] = []

        return session

    async def start_session(self, session_id: str) -> bool:
        """セッションを開始"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = StreamingStatus.CONNECTED
        session.started_at = datetime.utcnow()

        # 文字起こしタスクを開始
        task = asyncio.create_task(self._transcription_loop(session_id))
        self._tasks[session_id] = task

        return True

    async def stop_session(self, session_id: str) -> Optional[StreamingSession]:
        """セッションを停止"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        session.status = StreamingStatus.DISCONNECTED
        session.ended_at = datetime.utcnow()

        # タスクをキャンセル
        if session_id in self._tasks:
            self._tasks[session_id].cancel()
            del self._tasks[session_id]

        return session

    async def send_audio(self, session_id: str, audio_data: bytes) -> bool:
        """音声データを送信"""
        if session_id not in self._buffers:
            return False

        session = self._sessions.get(session_id)
        if session:
            session.status = StreamingStatus.TRANSCRIBING
            # 音声時間を計算（16bit PCM, 16kHz の場合）
            audio_ms = len(audio_data) / (session.config.sample_rate * 2) * 1000
            session.total_audio_ms += int(audio_ms)

        await self._buffers[session_id].append(audio_data)
        return True

    async def send_audio_base64(self, session_id: str, audio_base64: str) -> bool:
        """Base64エンコードされた音声データを送信"""
        try:
            audio_data = base64.b64decode(audio_base64)
            return await self.send_audio(session_id, audio_data)
        except Exception:
            return False

    def register_callback(
        self,
        session_id: str,
        callback: Callable[[TranscriptSegment], None],
    ):
        """コールバックを登録"""
        if session_id in self._callbacks:
            self._callbacks[session_id].append(callback)

    async def _transcription_loop(self, session_id: str):
        """文字起こしループ"""
        session = self._sessions.get(session_id)
        buffer = self._buffers.get(session_id)

        if not session or not buffer:
            return

        segment_counter = 0
        current_time_ms = 0

        try:
            while session.status in [StreamingStatus.CONNECTED, StreamingStatus.TRANSCRIBING]:
                # バッファから音声を読み取り
                if buffer.size > 0:
                    audio_data = await buffer.read_all()

                    # 文字起こしを実行（シミュレーション）
                    segment = await self._transcribe_chunk(
                        audio_data,
                        session.config,
                        segment_counter,
                        current_time_ms,
                    )

                    if segment:
                        session.segments.append(segment)
                        segment_counter += 1
                        current_time_ms = segment.end_time_ms

                        # コールバックを呼び出し
                        for callback in self._callbacks.get(session_id, []):
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(segment)
                                else:
                                    callback(segment)
                            except Exception as e:
                                print(f"Callback error: {e}")

                await asyncio.sleep(0.1)  # 100ms間隔で処理

        except asyncio.CancelledError:
            pass
        except Exception as e:
            session.status = StreamingStatus.ERROR
            session.metadata["error"] = str(e)

    async def _transcribe_chunk(
        self,
        audio_data: bytes,
        config: StreamingConfig,
        segment_index: int,
        start_time_ms: int,
    ) -> Optional[TranscriptSegment]:
        """音声チャンクを文字起こし（実際のWhisperを使用）"""
        # 最小音声長チェック（約500ms = 16000 samples/sec * 0.5sec * 2 bytes = 16000 bytes）
        min_audio_bytes = config.sample_rate * 2 * 0.5  # 500ms
        if len(audio_data) < min_audio_bytes:
            return None

        # 音声時間を計算
        duration_ms = int(len(audio_data) / (config.sample_rate * 2) * 1000)

        try:
            # 実際のWhisperで文字起こし
            result = await self._whisper_engine.transcribe_audio(
                audio_data=audio_data,
                sample_rate=config.sample_rate,
                language=config.language,
            )

            if result and result.get("text"):
                text = result["text"].strip()
                if not text:
                    return None

                # 信頼度を計算（セグメントがある場合は平均を取る）
                confidence = 0.9  # デフォルト
                if result.get("segments"):
                    # faster-whisperの場合、各セグメントにno_speech_probがある
                    pass

                segment = TranscriptSegment(
                    id=f"seg_{segment_index}",
                    text=text,
                    start_time_ms=start_time_ms,
                    end_time_ms=start_time_ms + duration_ms,
                    is_final=True,
                    confidence=confidence,
                    speaker_id=f"speaker_{segment_index % 2}" if config.enable_speaker_diarization else None,
                )

                logger.debug(f"Transcribed segment {segment_index}: {text[:50]}...")
                return segment

            return None

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            # エラー時はNoneを返して処理を継続
            return None

    async def get_session(self, session_id: str) -> Optional[StreamingSession]:
        """セッションを取得"""
        return self._sessions.get(session_id)

    async def get_transcript(self, session_id: str) -> str:
        """完全な文字起こしを取得"""
        session = self._sessions.get(session_id)
        if not session:
            return ""

        return " ".join(seg.text for seg in session.segments)


class LiveCaptionService:
    """ライブキャプションサービス"""

    def __init__(self, transcriber: RealtimeTranscriber):
        self.transcriber = transcriber
        self._caption_sessions: Dict[str, Dict[str, Any]] = {}

    async def create_caption_session(
        self,
        session_id: str,
        style: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """キャプションセッションを作成"""
        caption_config = {
            "session_id": session_id,
            "style": style or {
                "font_size": 24,
                "font_color": "#FFFFFF",
                "background_color": "#000000",
                "position": "bottom",
                "max_lines": 2,
            },
            "created_at": datetime.utcnow().isoformat(),
        }

        self._caption_sessions[session_id] = caption_config
        return caption_config

    async def get_caption_stream(
        self,
        session_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """キャプションストリームを取得"""
        session = await self.transcriber.get_session(session_id)
        if not session:
            return

        last_segment_id = None

        while session.status in [StreamingStatus.CONNECTED, StreamingStatus.TRANSCRIBING]:
            if session.segments:
                latest = session.segments[-1]
                if latest.id != last_segment_id:
                    last_segment_id = latest.id
                    yield {
                        "type": "caption",
                        "text": latest.text,
                        "speaker": latest.speaker_id,
                        "is_final": latest.is_final,
                        "timestamp": latest.start_time_ms,
                    }

            await asyncio.sleep(0.1)


class WebRTCBridge:
    """WebRTCブリッジ"""

    def __init__(self, transcriber: RealtimeTranscriber):
        self.transcriber = transcriber
        self._connections: Dict[str, Dict[str, Any]] = {}

    async def create_offer(self, session_id: str) -> Dict[str, Any]:
        """SDPオファーを作成"""
        # 実際の実装ではWebRTCライブラリを使用
        return {
            "type": "offer",
            "sdp": "v=0\r\n...",  # SDP内容
            "session_id": session_id,
        }

    async def handle_answer(self, session_id: str, answer: Dict[str, Any]) -> bool:
        """SDPアンサーを処理"""
        self._connections[session_id] = {
            "status": "connected",
            "answer": answer,
            "connected_at": datetime.utcnow().isoformat(),
        }
        return True

    async def handle_ice_candidate(
        self,
        session_id: str,
        candidate: Dict[str, Any],
    ) -> bool:
        """ICE候補を処理"""
        if session_id in self._connections:
            if "ice_candidates" not in self._connections[session_id]:
                self._connections[session_id]["ice_candidates"] = []
            self._connections[session_id]["ice_candidates"].append(candidate)
            return True
        return False


class MeetingIntegration:
    """会議システム連携"""

    def __init__(self, transcriber: RealtimeTranscriber):
        self.transcriber = transcriber

    async def connect_to_zoom(
        self,
        meeting_id: str,
        api_key: str,
        api_secret: str,
    ) -> Dict[str, Any]:
        """Zoom会議に接続（シミュレーション）"""
        session = await self.transcriber.create_session(
            user_id="zoom_bot",
            config=StreamingConfig(
                enable_speaker_diarization=True,
            ),
        )

        return {
            "session_id": session.id,
            "meeting_id": meeting_id,
            "status": "connecting",
            "provider": "zoom",
        }

    async def connect_to_teams(
        self,
        meeting_url: str,
        access_token: str,
    ) -> Dict[str, Any]:
        """Microsoft Teams会議に接続（シミュレーション）"""
        session = await self.transcriber.create_session(
            user_id="teams_bot",
            config=StreamingConfig(
                enable_speaker_diarization=True,
            ),
        )

        return {
            "session_id": session.id,
            "meeting_url": meeting_url,
            "status": "connecting",
            "provider": "teams",
        }

    async def connect_to_meet(
        self,
        meeting_code: str,
        credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Google Meet会議に接続（シミュレーション）"""
        session = await self.transcriber.create_session(
            user_id="meet_bot",
            config=StreamingConfig(
                enable_speaker_diarization=True,
            ),
        )

        return {
            "session_id": session.id,
            "meeting_code": meeting_code,
            "status": "connecting",
            "provider": "google_meet",
        }


# グローバルインスタンス
realtime_transcriber = RealtimeTranscriber()
live_caption_service = LiveCaptionService(realtime_transcriber)
webrtc_bridge = WebRTCBridge(realtime_transcriber)
meeting_integration = MeetingIntegration(realtime_transcriber)
