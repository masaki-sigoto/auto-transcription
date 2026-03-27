"""音声処理APIエンドポイント"""

import os
import tempfile
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.audio_processing_service import (
    AudioProcessingService,
    AudioSegmentationService,
    AudioQuality,
    AudioAnalysisResult,
)

router = APIRouter(prefix="/audio", tags=["audio-processing"])


class AudioAnalysisResponse(BaseModel):
    quality: str
    snr_db: float
    loudness_lufs: float
    clipping_percentage: float
    silence_percentage: float
    sample_rate: int
    channels: int
    duration_seconds: float
    issues: list[str]
    recommendations: list[str]


class EnhancementRequest(BaseModel):
    noise_reduction: bool = True
    voice_enhancement: bool = True
    normalize: bool = True
    noise_reduction_level: float = 0.5


class EnhancementResponse(BaseModel):
    original_quality: str
    enhanced_quality: str
    improvements: list[str]
    download_url: str


@router.post("/analyze", response_model=AudioAnalysisResponse)
async def analyze_audio(
    file: UploadFile = File(...),
):
    """音声ファイルを分析"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        service = AudioProcessingService()
        result = await service.analyze_audio(tmp_path)

        return AudioAnalysisResponse(
            quality=result.quality.value,
            snr_db=result.snr_db,
            loudness_lufs=result.loudness_lufs,
            clipping_percentage=result.clipping_percentage,
            silence_percentage=result.silence_percentage,
            sample_rate=result.sample_rate,
            channels=result.channels,
            duration_seconds=result.duration_seconds,
            issues=result.issues,
            recommendations=result.recommendations,
        )
    finally:
        os.unlink(tmp_path)


@router.post("/enhance")
async def enhance_audio(
    file: UploadFile = File(...),
    noise_reduction: bool = True,
    voice_enhancement: bool = True,
    normalize: bool = True,
    background_tasks: BackgroundTasks = None,
):
    """音声を強調処理"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_in:
        content = await file.read()
        tmp_in.write(content)
        input_path = tmp_in.name

    output_path = tempfile.mktemp(suffix="_enhanced.wav")

    try:
        service = AudioProcessingService()

        # 初期分析
        initial_result = await service.analyze_audio(input_path)

        # 強調処理
        _, final_result = await service.full_enhancement_pipeline(
            input_path,
            output_path,
            noise_reduction=noise_reduction,
            voice_enhancement=voice_enhancement,
            normalize=normalize,
        )

        # 改善点を計算
        improvements = []
        if final_result.snr_db > initial_result.snr_db:
            improvements.append(f"SNR: {initial_result.snr_db:.1f}dB → {final_result.snr_db:.1f}dB")
        if abs(final_result.loudness_lufs - (-16)) < abs(initial_result.loudness_lufs - (-16)):
            improvements.append(f"ラウドネス: {initial_result.loudness_lufs:.1f} → {final_result.loudness_lufs:.1f} LUFS")
        if final_result.clipping_percentage < initial_result.clipping_percentage:
            improvements.append("クリッピング低減")

        # ファイルを返す（実際のアプリではS3等にアップロード）
        from fastapi.responses import FileResponse

        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=f"enhanced_{file.filename}",
            headers={
                "X-Original-Quality": initial_result.quality.value,
                "X-Enhanced-Quality": final_result.quality.value,
                "X-Improvements": ",".join(improvements),
            },
        )
    finally:
        os.unlink(input_path)
        # output_pathはFileResponseが送信後に削除


@router.post("/denoise")
async def denoise_audio(
    file: UploadFile = File(...),
    level: float = 0.5,
):
    """ノイズ除去"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_in:
        content = await file.read()
        tmp_in.write(content)
        input_path = tmp_in.name

    output_path = tempfile.mktemp(suffix="_denoised.wav")

    try:
        service = AudioProcessingService()
        await service.remove_noise(input_path, output_path, level)

        from fastapi.responses import FileResponse
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=f"denoised_{file.filename}",
        )
    finally:
        os.unlink(input_path)


@router.post("/normalize")
async def normalize_audio(
    file: UploadFile = File(...),
    target_lufs: float = -16.0,
):
    """音量正規化"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_in:
        content = await file.read()
        tmp_in.write(content)
        input_path = tmp_in.name

    output_path = tempfile.mktemp(suffix="_normalized.wav")

    try:
        service = AudioProcessingService()
        await service.normalize_audio(input_path, output_path, target_lufs)

        from fastapi.responses import FileResponse
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=f"normalized_{file.filename}",
        )
    finally:
        os.unlink(input_path)


@router.post("/detect-speech")
async def detect_speech_segments(
    file: UploadFile = File(...),
    min_speech_duration: float = 0.5,
    min_silence_duration: float = 0.3,
):
    """音声区間を検出"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        service = AudioSegmentationService()
        segments = await service.detect_speech_segments(
            tmp_path,
            min_speech_duration=min_speech_duration,
            min_silence_duration=min_silence_duration,
        )

        return {
            "segments": [
                {"start": start, "end": end, "duration": end - start}
                for start, end in segments
            ],
            "total_segments": len(segments),
            "total_speech_duration": sum(end - start for start, end in segments),
        }
    finally:
        os.unlink(tmp_path)


@router.post("/convert")
async def convert_audio(
    file: UploadFile = File(...),
    target_format: str = "wav",
    sample_rate: int = 16000,
    channels: int = 1,
):
    """音声フォーマット変換"""
    import subprocess

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # 入力ファイル拡張子
    input_ext = os.path.splitext(file.filename)[1] or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=input_ext) as tmp_in:
        content = await file.read()
        tmp_in.write(content)
        input_path = tmp_in.name

    output_path = tempfile.mktemp(suffix=f".{target_format}")

    try:
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-y",
            output_path,
        ]

        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Conversion failed: {process.stderr}")

        from fastapi.responses import FileResponse

        base_name = os.path.splitext(file.filename)[0]
        return FileResponse(
            output_path,
            media_type=f"audio/{target_format}",
            filename=f"{base_name}.{target_format}",
        )
    finally:
        os.unlink(input_path)
