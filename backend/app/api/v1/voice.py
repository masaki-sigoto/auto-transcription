"""音声クローン・カスタム音声APIエンドポイント"""

import uuid
import base64
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.voice_clone_service import (
    voice_clone_engine,
    voice_conversion_engine,
    custom_tts_engine,
    voice_regenerator,
    speaker_voice_manager,
    VoiceProvider,
    VoiceGender,
    VoiceStyle,
)

router = APIRouter(prefix="/voice", tags=["voice"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tenant_id() -> str:
    return "default-tenant"


# === 音声クローン ===

class StartVoiceCloneRequest(BaseModel):
    name: str
    source_speaker_id: Optional[str] = None
    provider: VoiceProvider = VoiceProvider.ELEVENLABS


@router.post("/clone")
async def start_voice_clone(
    request: StartVoiceCloneRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """音声クローンを開始"""
    voice = await voice_clone_engine.start_voice_clone(
        name=request.name,
        tenant_id=tenant_id,
        source_speaker_id=request.source_speaker_id,
        provider=request.provider,
    )

    return {
        "voice_id": voice.id,
        "name": voice.name,
        "status": voice.status,
        "created_at": voice.created_at.isoformat(),
        "next_step": "Upload training samples using POST /voice/clone/{voice_id}/samples",
    }


@router.post("/clone/{voice_id}/samples")
async def add_training_sample(
    voice_id: str,
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """学習サンプルを追加"""
    audio_data = await file.read()

    try:
        result = await voice_clone_engine.add_training_sample(voice_id, audio_data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/clone/{voice_id}/train")
async def train_voice(
    voice_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """音声をトレーニング"""
    try:
        voice = await voice_clone_engine.train_voice(voice_id)
        return {
            "voice_id": voice.id,
            "status": voice.status,
            "quality_score": voice.quality_score,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/clone/{voice_id}")
async def get_cloned_voice(
    voice_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """クローン音声を取得"""
    voice = await voice_clone_engine.get_cloned_voice(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    return {
        "id": voice.id,
        "name": voice.name,
        "status": voice.status,
        "training_samples": voice.training_samples,
        "quality_score": voice.quality_score,
        "created_at": voice.created_at.isoformat(),
    }


@router.get("/clone")
async def list_cloned_voices(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """クローン音声一覧"""
    voices = await voice_clone_engine.list_cloned_voices(tenant_id)

    return {
        "voices": [
            {
                "id": v.id,
                "name": v.name,
                "status": v.status,
                "training_samples": v.training_samples,
                "quality_score": v.quality_score,
            }
            for v in voices
        ],
        "count": len(voices),
    }


@router.delete("/clone/{voice_id}")
async def delete_cloned_voice(
    voice_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """クローン音声を削除"""
    success = await voice_clone_engine.delete_cloned_voice(voice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Voice not found")

    return {"status": "deleted", "voice_id": voice_id}


# === 音声変換 ===

@router.post("/convert")
async def convert_voice(
    target_voice_id: str,
    file: UploadFile = File(...),
    preserve_prosody: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """音声を変換"""
    audio_data = await file.read()

    try:
        result = await voice_conversion_engine.convert_voice(
            source_audio=audio_data,
            target_voice_id=target_voice_id,
            preserve_prosody=preserve_prosody,
        )

        return {
            "conversion_id": result.id,
            "target_voice_id": result.target_voice_id,
            "duration_ms": result.duration_ms,
            "created_at": result.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === TTS ===

class SynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    style: VoiceStyle = VoiceStyle.NEUTRAL
    speed: float = 1.0
    pitch: float = 1.0


@router.post("/synthesize")
async def synthesize_speech(
    request: SynthesizeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """音声を合成"""
    try:
        result = await custom_tts_engine.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            style=request.style,
            speed=request.speed,
            pitch=request.pitch,
        )

        return {
            "id": result.id,
            "voice_id": result.voice_id,
            "duration_ms": result.duration_ms,
            "format": result.format,
            "audio_base64": base64.b64encode(result.audio_data).decode(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/synthesize/audio")
async def synthesize_speech_audio(
    request: SynthesizeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """音声を合成（バイナリ返却）"""
    try:
        result = await custom_tts_engine.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            style=request.style,
            speed=request.speed,
            pitch=request.pitch,
        )

        return Response(
            content=result.audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=speech_{result.id}.wav"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SynthesizeSSMLRequest(BaseModel):
    ssml: str
    voice_id: str


@router.post("/synthesize/ssml")
async def synthesize_ssml(
    request: SynthesizeSSMLRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """SSMLで音声を合成"""
    try:
        result = await custom_tts_engine.synthesize_ssml(
            ssml=request.ssml,
            voice_id=request.voice_id,
        )

        return {
            "id": result.id,
            "voice_id": result.voice_id,
            "duration_ms": result.duration_ms,
            "audio_base64": base64.b64encode(result.audio_data).decode(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === 音声一覧 ===

@router.get("/voices")
async def list_voices(
    language: Optional[str] = None,
    gender: Optional[VoiceGender] = None,
):
    """利用可能な音声一覧"""
    voices = custom_tts_engine.list_voices(language=language, gender=gender)

    return {
        "voices": [
            {
                "id": v.id,
                "name": v.name,
                "description": v.description,
                "gender": v.gender.value,
                "language": v.language,
                "provider": v.provider.value,
                "is_cloned": v.is_cloned,
            }
            for v in voices
        ],
        "count": len(voices),
    }


@router.get("/voices/{voice_id}")
async def get_voice(voice_id: str):
    """音声詳細を取得"""
    voices = custom_tts_engine.list_voices()
    voice = next((v for v in voices if v.id == voice_id), None)

    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    return {
        "id": voice.id,
        "name": voice.name,
        "description": voice.description,
        "gender": voice.gender.value,
        "language": voice.language,
        "provider": voice.provider.value,
        "is_cloned": voice.is_cloned,
        "settings": voice.settings,
    }


# === 音声再生成 ===

class RegenerateRequest(BaseModel):
    original_text: str
    translated_text: str
    voice_id: str
    preserve_timing: bool = True


@router.post("/regenerate")
async def regenerate_voice(
    request: RegenerateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """翻訳テキストで音声を再生成"""
    try:
        result = await voice_regenerator.regenerate_in_language(
            original_text=request.original_text,
            translated_text=request.translated_text,
            voice_id=request.voice_id,
            preserve_timing=request.preserve_timing,
        )

        return {
            "id": result.id,
            "voice_id": result.voice_id,
            "duration_ms": result.duration_ms,
            "audio_base64": base64.b64encode(result.audio_data).decode(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === 話者音声マッピング ===

class SetSpeakerVoiceRequest(BaseModel):
    speaker_id: str
    voice_id: str


@router.post("/speaker-mapping")
async def set_speaker_voice(
    request: SetSpeakerVoiceRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """話者に音声を割り当て"""
    await speaker_voice_manager.set_speaker_voice(
        tenant_id=tenant_id,
        speaker_id=request.speaker_id,
        voice_id=request.voice_id,
    )

    return {
        "speaker_id": request.speaker_id,
        "voice_id": request.voice_id,
        "status": "assigned",
    }


@router.get("/speaker-mapping")
async def list_speaker_mappings(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """話者マッピング一覧"""
    mappings = await speaker_voice_manager.list_speaker_mappings(tenant_id)

    return {
        "mappings": [
            {"speaker_id": sid, "voice_id": vid}
            for sid, vid in mappings.items()
        ],
        "count": len(mappings),
    }


class AutoAssignRequest(BaseModel):
    speaker_ids: List[str]
    available_voice_ids: List[str]


@router.post("/speaker-mapping/auto-assign")
async def auto_assign_voices(
    request: AutoAssignRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """音声を自動割り当て"""
    mappings = await speaker_voice_manager.auto_assign_voices(
        tenant_id=tenant_id,
        speaker_ids=request.speaker_ids,
        available_voices=request.available_voice_ids,
    )

    return {
        "mappings": [
            {"speaker_id": sid, "voice_id": vid}
            for sid, vid in mappings.items()
        ],
        "count": len(mappings),
    }


# === スタイル情報 ===

@router.get("/styles")
async def list_voice_styles():
    """音声スタイル一覧"""
    return {
        "styles": [
            {"id": VoiceStyle.NEUTRAL.value, "name": "ニュートラル", "description": "標準的なトーン"},
            {"id": VoiceStyle.CHEERFUL.value, "name": "明るい", "description": "明るく元気なトーン"},
            {"id": VoiceStyle.SERIOUS.value, "name": "真剣", "description": "真剣で落ち着いたトーン"},
            {"id": VoiceStyle.PROFESSIONAL.value, "name": "プロフェッショナル", "description": "ビジネス向けのトーン"},
            {"id": VoiceStyle.FRIENDLY.value, "name": "フレンドリー", "description": "親しみやすいトーン"},
            {"id": VoiceStyle.NARRATION.value, "name": "ナレーション", "description": "ナレーション向けのトーン"},
        ]
    }
