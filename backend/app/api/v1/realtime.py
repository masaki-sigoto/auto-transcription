"""リアルタイムストリーミング文字起こしAPIエンドポイント"""

import uuid
import json
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.realtime_transcription_service import (
    realtime_transcriber,
    live_caption_service,
    webrtc_bridge,
    meeting_integration,
    StreamingConfig,
    StreamingStatus,
    AudioFormat,
    StreamingSession,
)
from app.core.database import get_db
from app.models.transcription import Transcription, Segment, Speaker

router = APIRouter(prefix="/realtime", tags=["realtime"])
logger = logging.getLogger(__name__)


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === セッション管理 ===

class CreateSessionRequest(BaseModel):
    language: str = "ja"
    sample_rate: int = 16000
    channels: int = 1
    audio_format: AudioFormat = AudioFormat.PCM_16
    enable_interim_results: bool = True
    enable_speaker_diarization: bool = False
    model: str = "whisper-large-v3"


@router.post("/sessions")
async def create_session(
    request: CreateSessionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ストリーミングセッションを作成"""
    config = StreamingConfig(
        sample_rate=request.sample_rate,
        channels=request.channels,
        audio_format=request.audio_format,
        language=request.language,
        enable_interim_results=request.enable_interim_results,
        enable_speaker_diarization=request.enable_speaker_diarization,
        model=request.model,
    )

    session = await realtime_transcriber.create_session(
        user_id=str(user_id),
        config=config,
    )

    return {
        "session_id": session.id,
        "status": session.status.value,
        "config": {
            "sample_rate": config.sample_rate,
            "channels": config.channels,
            "audio_format": config.audio_format.value,
            "language": config.language,
        },
        "websocket_url": f"/api/v1/realtime/ws/{session.id}",
        "created_at": session.created_at.isoformat(),
    }


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セッションを開始"""
    success = await realtime_transcriber.start_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await realtime_transcriber.get_session(session_id)
    return {
        "session_id": session_id,
        "status": session.status.value,
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: str,
    save_to_db: bool = Query(True, description="結果をDBに保存するか"),
    title: Optional[str] = Query(None, description="保存時のタイトル"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """セッションを停止し、オプションでDBに保存"""
    session = await realtime_transcriber.stop_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    transcription_id = None

    # DBに保存
    if save_to_db and session.segments:
        try:
            transcription_id = await _save_session_to_db(
                db=db,
                session=session,
                user_id=user_id,
                title=title or f"リアルタイム文字起こし {session.created_at.strftime('%Y-%m-%d %H:%M')}",
            )
            logger.info(f"Saved realtime session {session_id} to DB as transcription {transcription_id}")
        except Exception as e:
            logger.error(f"Failed to save session to DB: {e}")

    return {
        "session_id": session_id,
        "status": session.status.value,
        "total_audio_ms": session.total_audio_ms,
        "segments_count": len(session.segments),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "transcription_id": str(transcription_id) if transcription_id else None,
    }


async def _save_session_to_db(
    db: AsyncSession,
    session: StreamingSession,
    user_id: uuid.UUID,
    title: str,
) -> uuid.UUID:
    """リアルタイムセッションをDBに保存"""
    # Transcriptionレコードを作成
    transcription = Transcription(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        status="completed",
        audio_url=f"realtime://{session.id}",  # リアルタイムセッションを示す仮のURL
        audio_duration_sec=session.total_audio_ms // 1000 if session.total_audio_ms else 0,
        language=session.config.language,
        engine="realtime-whisper",
        enable_diarization=session.config.enable_speaker_diarization,
        enable_llm_correction=False,
    )
    db.add(transcription)

    # 話者情報を作成（話者分離が有効な場合）
    speaker_map = {}
    if session.config.enable_speaker_diarization:
        unique_speakers = set(seg.speaker_id for seg in session.segments if seg.speaker_id)
        colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"]

        for i, speaker_label in enumerate(unique_speakers):
            speaker = Speaker(
                id=uuid.uuid4(),
                transcription_id=transcription.id,
                label=speaker_label or f"話者{i+1}",
                color=colors[i % len(colors)],
            )
            db.add(speaker)
            speaker_map[speaker_label] = speaker.id

    # セグメントを作成
    for seg in session.segments:
        segment = Segment(
            id=uuid.uuid4(),
            transcription_id=transcription.id,
            speaker_id=speaker_map.get(seg.speaker_id) if seg.speaker_id else None,
            start_time_ms=seg.start_time_ms,
            end_time_ms=seg.end_time_ms,
            text=seg.text,
            confidence=seg.confidence,
            is_edited=False,
        )
        db.add(segment)

    await db.commit()
    return transcription.id


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セッション情報を取得"""
    session = await realtime_transcriber.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.id,
        "status": session.status.value,
        "total_audio_ms": session.total_audio_ms,
        "segments_count": len(session.segments),
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


@router.get("/sessions/{session_id}/transcript")
async def get_transcript(
    session_id: str,
    format: str = Query("text", enum=["text", "json", "srt", "vtt"]),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こし結果を取得"""
    session = await realtime_transcriber.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if format == "text":
        text = await realtime_transcriber.get_transcript(session_id)
        return {"transcript": text}

    elif format == "json":
        return {
            "segments": [
                {
                    "id": seg.id,
                    "text": seg.text,
                    "start_time_ms": seg.start_time_ms,
                    "end_time_ms": seg.end_time_ms,
                    "speaker_id": seg.speaker_id,
                    "confidence": seg.confidence,
                    "is_final": seg.is_final,
                }
                for seg in session.segments
            ]
        }

    elif format == "srt":
        srt_content = _generate_srt(session.segments)
        return {"srt": srt_content}

    elif format == "vtt":
        vtt_content = _generate_vtt(session.segments)
        return {"vtt": vtt_content}


def _generate_srt(segments) -> str:
    """SRT形式を生成"""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _ms_to_srt_time(seg.start_time_ms)
        end = _ms_to_srt_time(seg.end_time_ms)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def _generate_vtt(segments) -> str:
    """WebVTT形式を生成"""
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = _ms_to_vtt_time(seg.start_time_ms)
        end = _ms_to_vtt_time(seg.end_time_ms)
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def _ms_to_srt_time(ms: int) -> str:
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _ms_to_vtt_time(ms: int) -> str:
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


# === WebSocket ===

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
):
    """WebSocketエンドポイント"""
    await websocket.accept()

    session = await realtime_transcriber.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    # セッションを開始
    await realtime_transcriber.start_session(session_id)

    # コールバックを登録
    async def send_segment(segment):
        try:
            await websocket.send_json({
                "type": "transcript",
                "segment": {
                    "id": segment.id,
                    "text": segment.text,
                    "start_time_ms": segment.start_time_ms,
                    "end_time_ms": segment.end_time_ms,
                    "is_final": segment.is_final,
                    "confidence": segment.confidence,
                    "speaker_id": segment.speaker_id,
                },
            })
        except Exception:
            pass

    realtime_transcriber.register_callback(session_id, send_segment)

    try:
        while True:
            data = await websocket.receive()

            if data["type"] == "websocket.disconnect":
                break

            if "bytes" in data:
                # バイナリ音声データ
                await realtime_transcriber.send_audio(session_id, data["bytes"])

            elif "text" in data:
                # JSONメッセージ
                message = json.loads(data["text"])

                if message.get("type") == "audio":
                    # Base64エンコードされた音声
                    await realtime_transcriber.send_audio_base64(
                        session_id,
                        message["data"],
                    )

                elif message.get("type") == "control":
                    # 制御メッセージ
                    if message.get("action") == "pause":
                        session.status = StreamingStatus.PAUSED
                    elif message.get("action") == "resume":
                        session.status = StreamingStatus.TRANSCRIBING

    except WebSocketDisconnect:
        pass
    finally:
        await realtime_transcriber.stop_session(session_id)


# === ライブキャプション ===

class CreateCaptionRequest(BaseModel):
    session_id: str
    font_size: int = 24
    font_color: str = "#FFFFFF"
    background_color: str = "#000000"
    position: str = "bottom"
    max_lines: int = 2


@router.post("/captions")
async def create_caption_session(
    request: CreateCaptionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """キャプションセッションを作成"""
    caption = await live_caption_service.create_caption_session(
        session_id=request.session_id,
        style={
            "font_size": request.font_size,
            "font_color": request.font_color,
            "background_color": request.background_color,
            "position": request.position,
            "max_lines": request.max_lines,
        },
    )

    return caption


@router.websocket("/captions/ws/{session_id}")
async def caption_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """キャプションWebSocket"""
    await websocket.accept()

    try:
        async for caption in live_caption_service.get_caption_stream(session_id):
            await websocket.send_json(caption)
    except WebSocketDisconnect:
        pass


# === WebRTC ===

@router.post("/webrtc/{session_id}/offer")
async def create_webrtc_offer(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """WebRTCオファーを作成"""
    offer = await webrtc_bridge.create_offer(session_id)
    return offer


class WebRTCAnswerRequest(BaseModel):
    sdp: str
    type: str


@router.post("/webrtc/{session_id}/answer")
async def handle_webrtc_answer(
    session_id: str,
    request: WebRTCAnswerRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """WebRTCアンサーを処理"""
    success = await webrtc_bridge.handle_answer(
        session_id,
        {"sdp": request.sdp, "type": request.type},
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to handle answer")

    return {"status": "connected"}


class ICECandidateRequest(BaseModel):
    candidate: str
    sdpMid: str
    sdpMLineIndex: int


@router.post("/webrtc/{session_id}/ice-candidate")
async def handle_ice_candidate(
    session_id: str,
    request: ICECandidateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ICE候補を処理"""
    success = await webrtc_bridge.handle_ice_candidate(
        session_id,
        {
            "candidate": request.candidate,
            "sdpMid": request.sdpMid,
            "sdpMLineIndex": request.sdpMLineIndex,
        },
    )

    if not success:
        raise HTTPException(status_code=400, detail="Session not found")

    return {"status": "added"}


# === 会議連携 ===

class ZoomConnectRequest(BaseModel):
    meeting_id: str
    api_key: str
    api_secret: str


@router.post("/meetings/zoom")
async def connect_to_zoom(
    request: ZoomConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Zoom会議に接続"""
    result = await meeting_integration.connect_to_zoom(
        meeting_id=request.meeting_id,
        api_key=request.api_key,
        api_secret=request.api_secret,
    )
    return result


class TeamsConnectRequest(BaseModel):
    meeting_url: str
    access_token: str


@router.post("/meetings/teams")
async def connect_to_teams(
    request: TeamsConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Microsoft Teams会議に接続"""
    result = await meeting_integration.connect_to_teams(
        meeting_url=request.meeting_url,
        access_token=request.access_token,
    )
    return result


class MeetConnectRequest(BaseModel):
    meeting_code: str


@router.post("/meetings/google-meet")
async def connect_to_meet(
    request: MeetConnectRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Google Meet会議に接続"""
    result = await meeting_integration.connect_to_meet(
        meeting_code=request.meeting_code,
        credentials={},  # OAuth認証が必要
    )
    return result


# === 設定 ===

@router.get("/models")
async def list_realtime_models():
    """利用可能なリアルタイムモデル一覧"""
    return {
        "models": [
            {
                "id": "whisper-large-v3",
                "name": "Whisper Large V3",
                "latency": "medium",
                "accuracy": "high",
                "languages": ["ja", "en", "zh", "ko", "multi"],
            },
            {
                "id": "whisper-medium",
                "name": "Whisper Medium",
                "latency": "low",
                "accuracy": "medium",
                "languages": ["ja", "en", "zh", "ko", "multi"],
            },
            {
                "id": "streaming-asr-ja",
                "name": "Streaming ASR (Japanese)",
                "latency": "very_low",
                "accuracy": "high",
                "languages": ["ja"],
            },
        ]
    }
