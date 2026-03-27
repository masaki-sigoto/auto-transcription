import asyncio
import json
import base64
import tempfile
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import uuid

from app.services.transcription_engine import get_engine, TranscriptionSegment

router = APIRouter()


class RealtimeTranscriptionManager:
    """リアルタイム文字起こしセッション管理"""

    def __init__(self):
        self.active_sessions: dict[str, "RealtimeSession"] = {}

    async def create_session(
        self,
        websocket: WebSocket,
        user_id: str,
        language: str = "ja",
        engine: str = "reazon",
    ) -> "RealtimeSession":
        session_id = str(uuid.uuid4())
        session = RealtimeSession(
            session_id=session_id,
            websocket=websocket,
            user_id=user_id,
            language=language,
            engine=engine,
        )
        self.active_sessions[session_id] = session
        return session

    def remove_session(self, session_id: str):
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]


class RealtimeSession:
    """個別のリアルタイムセッション"""

    def __init__(
        self,
        session_id: str,
        websocket: WebSocket,
        user_id: str,
        language: str,
        engine: str,
    ):
        self.session_id = session_id
        self.websocket = websocket
        self.user_id = user_id
        self.language = language
        self.engine_name = engine
        self.audio_buffer = bytearray()
        self.segments: list[TranscriptionSegment] = []
        self.current_offset_ms = 0
        self.is_processing = False
        self.chunk_duration_ms = 5000  # 5秒ごとに処理

    async def process_audio_chunk(self, audio_data: bytes):
        """音声チャンクを処理"""
        self.audio_buffer.extend(audio_data)

        # バッファが一定サイズに達したら処理
        # 16kHz 16bit mono = 32000 bytes/sec
        chunk_size = (self.chunk_duration_ms * 32000) // 1000

        if len(self.audio_buffer) >= chunk_size and not self.is_processing:
            await self._transcribe_buffer()

    async def _transcribe_buffer(self):
        """バッファを文字起こし"""
        if self.is_processing or len(self.audio_buffer) == 0:
            return

        self.is_processing = True

        try:
            # 一時ファイルに書き出し
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                # WAVヘッダーを追加
                self._write_wav_header(f, len(self.audio_buffer))
                f.write(bytes(self.audio_buffer))
                temp_path = f.name

            try:
                # 文字起こし実行
                engine = get_engine(self.engine_name)
                result = await engine.transcribe(temp_path, self.language)

                # セグメントのオフセットを調整
                for seg in result.segments:
                    adjusted_segment = TranscriptionSegment(
                        start_time_ms=seg.start_time_ms + self.current_offset_ms,
                        end_time_ms=seg.end_time_ms + self.current_offset_ms,
                        text=seg.text,
                        confidence=seg.confidence,
                    )
                    self.segments.append(adjusted_segment)

                    # クライアントに送信
                    await self.websocket.send_json({
                        "type": "transcript",
                        "segment": {
                            "text": adjusted_segment.text,
                            "start_time_ms": adjusted_segment.start_time_ms,
                            "end_time_ms": adjusted_segment.end_time_ms,
                            "is_final": True,
                            "confidence": adjusted_segment.confidence,
                        }
                    })

                # オフセットを更新
                self.current_offset_ms += self.chunk_duration_ms

            finally:
                os.unlink(temp_path)

            # バッファをクリア
            self.audio_buffer.clear()

        except Exception as e:
            await self.websocket.send_json({
                "type": "error",
                "message": str(e),
            })

        finally:
            self.is_processing = False

    def _write_wav_header(self, f, data_size: int):
        """WAVヘッダーを書き込み"""
        import struct

        sample_rate = 16000
        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8

        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))  # Subchunk1Size
        f.write(struct.pack('<H', 1))   # AudioFormat (PCM)
        f.write(struct.pack('<H', num_channels))
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', byte_rate))
        f.write(struct.pack('<H', block_align))
        f.write(struct.pack('<H', bits_per_sample))
        f.write(b'data')
        f.write(struct.pack('<I', data_size))

    async def finalize(self) -> list[TranscriptionSegment]:
        """残りのバッファを処理してセッションを終了"""
        if len(self.audio_buffer) > 0:
            await self._transcribe_buffer()
        return self.segments


manager = RealtimeTranscriptionManager()


@router.websocket("/ws/realtime")
async def realtime_transcription(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    language: str = Query("ja"),
    engine: str = Query("reazon"),
):
    """リアルタイム文字起こしWebSocketエンドポイント"""
    await websocket.accept()

    # TODO: トークン検証
    user_id = "demo-user"

    session = await manager.create_session(
        websocket=websocket,
        user_id=user_id,
        language=language,
        engine=engine,
    )

    try:
        await websocket.send_json({
            "type": "session_started",
            "session_id": session.session_id,
        })

        while True:
            data = await websocket.receive_json()

            if data["type"] == "audio_chunk":
                # Base64デコード
                audio_bytes = base64.b64decode(data["data"])
                await session.process_audio_chunk(audio_bytes)

            elif data["type"] == "stop":
                # セッション終了
                segments = await session.finalize()
                await websocket.send_json({
                    "type": "session_ended",
                    "total_segments": len(segments),
                })
                break

    except WebSocketDisconnect:
        pass

    finally:
        manager.remove_session(session.session_id)
