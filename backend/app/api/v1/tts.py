"""音声合成・テキスト読み上げAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile
import os
import aiofiles

from app.services.tts_service import (
    TTSService,
    TranscriptionReadbackService,
    VoiceCloningService,
    TTSProvider,
    AudioFormat,
    VoiceGender,
)

router = APIRouter(prefix="/tts", tags=["tts"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === テキスト読み上げ ===

class SynthesizeRequest(BaseModel):
    text: str
    voice_id: str = "alloy"
    provider: TTSProvider = TTSProvider.OPENAI
    speed: float = 1.0
    pitch: float = 1.0
    format: AudioFormat = AudioFormat.MP3


class SynthesizeResponse(BaseModel):
    audio_url: str
    duration_sec: float
    format: str
    file_size_bytes: int


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_text(
    request: SynthesizeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テキストを音声に変換"""
    service = TTSService()

    try:
        result = await service.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            provider=request.provider,
            speed=request.speed,
            pitch=request.pitch,
            format=request.format,
        )

        return SynthesizeResponse(
            audio_url=f"/tts/audio/{os.path.basename(result.audio_path)}",
            duration_sec=result.duration_sec,
            format=result.format.value,
            file_size_bytes=result.file_size_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/{filename}")
async def get_audio_file(
    filename: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """生成された音声ファイルを取得"""
    file_path = os.path.join(tempfile.gettempdir(), filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    # ファイル拡張子からメディアタイプを決定
    ext = filename.split(".")[-1].lower()
    media_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
    }

    return FileResponse(
        file_path,
        media_type=media_types.get(ext, "audio/mpeg"),
    )


# === 音声一覧 ===

class VoiceResponse(BaseModel):
    id: str
    name: str
    language: str
    gender: str
    provider: str
    preview_url: Optional[str] = None
    description: Optional[str] = None


@router.get("/voices", response_model=List[VoiceResponse])
async def list_voices(
    provider: Optional[TTSProvider] = None,
    language: Optional[str] = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """利用可能な音声一覧を取得"""
    service = TTSService()

    voices = await service.list_voices(provider, language)

    return [
        VoiceResponse(
            id=v.id,
            name=v.name,
            language=v.language,
            gender=v.gender.value,
            provider=v.provider.value,
            preview_url=v.preview_url,
            description=v.description,
        )
        for v in voices
    ]


# === 文字起こし読み上げ ===

class SegmentInput(BaseModel):
    text: str
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    start_time_ms: int = 0
    end_time_ms: int = 0


class ReadbackRequest(BaseModel):
    segments: List[SegmentInput]
    voice_mapping: Optional[dict] = None
    provider: TTSProvider = TTSProvider.OPENAI
    format: AudioFormat = AudioFormat.MP3
    merge_audio: bool = True


@router.post("/readback")
async def generate_readback(
    request: ReadbackRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしセグメントから音声を生成"""
    service = TranscriptionReadbackService()

    segments = [
        {
            "text": seg.text,
            "speaker_id": seg.speaker_id,
            "speaker_name": seg.speaker_name,
            "start_time_ms": seg.start_time_ms,
            "end_time_ms": seg.end_time_ms,
        }
        for seg in request.segments
    ]

    result = await service.generate_readback(
        segments=segments,
        voice_mapping=request.voice_mapping,
        provider=request.provider,
        format=request.format,
    )

    if request.merge_audio and result["segments"]:
        merged_path = await service.merge_audio_segments(
            result["segments"],
            request.format,
        )
        result["merged_audio_url"] = f"/tts/audio/{os.path.basename(merged_path)}"

    # 個別セグメントのURLを設定
    for seg in result["segments"]:
        seg["audio_url"] = f"/tts/audio/{os.path.basename(seg['audio_path'])}"
        del seg["audio_path"]

    return result


@router.post("/readback/transcription/{transcription_id}")
async def generate_transcription_readback(
    transcription_id: str,
    voice_mapping: Optional[dict] = None,
    provider: TTSProvider = Query(TTSProvider.OPENAI),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしIDから音声を生成"""
    # 実際の実装ではDBからセグメントを取得
    # ここではサンプルデータ
    segments = [
        {
            "text": "これはサンプルの文字起こしテキストです。",
            "speaker_id": "speaker_1",
            "start_time_ms": 0,
            "end_time_ms": 5000,
        },
        {
            "text": "音声合成のデモンストレーションです。",
            "speaker_id": "speaker_2",
            "start_time_ms": 5000,
            "end_time_ms": 10000,
        },
    ]

    service = TranscriptionReadbackService()

    result = await service.generate_readback(
        segments=segments,
        voice_mapping=voice_mapping or {},
        provider=provider,
    )

    if result["segments"]:
        merged_path = await service.merge_audio_segments(result["segments"])
        result["merged_audio_url"] = f"/tts/audio/{os.path.basename(merged_path)}"

    for seg in result["segments"]:
        seg["audio_url"] = f"/tts/audio/{os.path.basename(seg['audio_path'])}"
        del seg["audio_path"]

    return result


# === 音声クローニング ===

@router.post("/voice-clone")
async def create_voice_clone(
    name: str,
    description: Optional[str] = None,
    files: List[UploadFile] = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """音声サンプルからクローンを作成"""
    service = VoiceCloningService()

    # ファイルを一時保存
    temp_files = []
    try:
        for file in files:
            temp_path = os.path.join(
                tempfile.gettempdir(),
                f"sample_{uuid.uuid4().hex}_{file.filename}"
            )
            async with aiofiles.open(temp_path, "wb") as f:
                content = await file.read()
                await f.write(content)
            temp_files.append(temp_path)

        voice = await service.create_voice_clone(
            name=name,
            audio_files=temp_files,
            description=description,
        )

        return {
            "voice_id": voice.id,
            "name": voice.name,
            "provider": voice.provider.value,
            "status": "created",
        }

    finally:
        # 一時ファイルを削除
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)


@router.delete("/voice-clone/{voice_id}")
async def delete_voice_clone(
    voice_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """クローン音声を削除"""
    service = VoiceCloningService()

    deleted = await service.delete_voice_clone(voice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Voice not found")

    return {"status": "deleted", "voice_id": voice_id}


# === プロバイダー情報 ===

@router.get("/providers")
async def list_providers(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """利用可能なTTSプロバイダー一覧"""
    return {
        "providers": [
            {
                "id": TTSProvider.OPENAI.value,
                "name": "OpenAI TTS",
                "description": "高品質な音声合成",
                "features": ["高速", "自然な発話", "多言語対応"],
                "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            },
            {
                "id": TTSProvider.GOOGLE.value,
                "name": "Google Cloud TTS",
                "description": "多言語・多声対応",
                "features": ["WaveNet", "SSML対応", "多声"],
            },
            {
                "id": TTSProvider.ELEVENLABS.value,
                "name": "ElevenLabs",
                "description": "超リアルな音声合成",
                "features": ["音声クローニング", "感情表現", "超自然"],
            },
        ]
    }


# === SSML構築 ===

class SSMLBuildRequest(BaseModel):
    segments: List[dict]  # {type: "text"|"pause"|"emphasis", content: str, ...}


@router.post("/ssml/build")
async def build_ssml(
    request: SSMLBuildRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """SSML文字列を構築"""
    from app.services.tts_service import SSMLBuilder

    builder = SSMLBuilder()

    for segment in request.segments:
        seg_type = segment.get("type", "text")

        if seg_type == "text":
            builder.text(segment.get("content", ""))
        elif seg_type == "pause":
            builder.pause(segment.get("time_ms", 500))
        elif seg_type == "emphasis":
            builder.emphasis(
                segment.get("content", ""),
                segment.get("level", "moderate"),
            )
        elif seg_type == "prosody":
            builder.prosody(
                segment.get("content", ""),
                rate=segment.get("rate"),
                pitch=segment.get("pitch"),
                volume=segment.get("volume"),
            )

    return {
        "ssml": builder.build(),
    }
