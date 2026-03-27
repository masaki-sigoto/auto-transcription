"""動画処理APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile
import os
import aiofiles

from app.services.video_processing_service import (
    VideoProcessingService,
    SubtitleService,
    MultimodalAnalysisService,
    VideoFormat,
    SubtitleFormat,
)

router = APIRouter(prefix="/video", tags=["video"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === 動画アップロード・処理 ===

class VideoUploadResponse(BaseModel):
    video_id: str
    status: str
    metadata: dict


class VideoProcessingRequest(BaseModel):
    video_id: str
    extract_audio: bool = True
    extract_frames: bool = True
    detect_scenes: bool = True
    detect_text: bool = True
    frame_interval_sec: float = 5.0


class VideoProcessingResponse(BaseModel):
    video_id: str
    status: str
    audio_path: Optional[str] = None
    frame_count: int = 0
    scene_count: int = 0
    detected_text_count: int = 0


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画をアップロード"""
    # ファイル保存
    video_id = str(uuid.uuid4())
    temp_path = os.path.join(tempfile.gettempdir(), f"{video_id}_{file.filename}")

    async with aiofiles.open(temp_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # メタデータ取得
    service = VideoProcessingService()
    try:
        metadata = await service.get_metadata(temp_path)
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail=f"Invalid video file: {str(e)}")

    return VideoUploadResponse(
        video_id=video_id,
        status="uploaded",
        metadata={
            "duration_sec": metadata.duration_sec,
            "resolution": f"{metadata.width}x{metadata.height}",
            "fps": metadata.fps,
            "codec": metadata.codec,
            "audio_codec": metadata.audio_codec,
            "file_size_bytes": metadata.file_size_bytes,
        },
    )


@router.post("/process", response_model=VideoProcessingResponse)
async def process_video(
    request: VideoProcessingRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画を処理"""
    service = MultimodalAnalysisService()

    # 実際の実装ではDBから動画パスを取得
    video_path = os.path.join(
        tempfile.gettempdir(),
        f"{request.video_id}_*.mp4"
    )

    # バックグラウンドで処理
    # 実際の実装ではCeleryタスクを使用

    return VideoProcessingResponse(
        video_id=request.video_id,
        status="processing",
        frame_count=0,
        scene_count=0,
        detected_text_count=0,
    )


# === 音声抽出 ===

@router.post("/extract-audio/{video_id}")
async def extract_audio(
    video_id: str,
    output_format: str = Query("wav", regex="^(wav|mp3)$"),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画から音声を抽出"""
    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    service = VideoProcessingService()
    audio_path = await service.extract_audio(video_path, output_format)

    return {
        "status": "completed",
        "audio_path": audio_path,
        "format": output_format,
    }


# === フレーム抽出 ===

class FrameExtractionRequest(BaseModel):
    video_id: str
    interval_sec: float = 1.0
    max_frames: int = 100


@router.post("/extract-frames")
async def extract_frames(
    request: FrameExtractionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画からフレームを抽出"""
    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{request.video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    service = VideoProcessingService()
    frames = await service.extract_frames(
        video_path,
        interval_sec=request.interval_sec,
        max_frames=request.max_frames,
    )

    return {
        "status": "completed",
        "frame_count": len(frames),
        "frames": [
            {
                "timestamp_ms": f.timestamp_ms,
                "image_path": f.image_path,
            }
            for f in frames
        ],
    }


# === シーン検出 ===

@router.post("/detect-scenes/{video_id}")
async def detect_scenes(
    video_id: str,
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """シーン変化を検出"""
    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    service = VideoProcessingService()
    scenes = await service.detect_scene_changes(video_path, threshold)

    return {
        "status": "completed",
        "scene_count": len(scenes),
        "scenes": [
            {
                "timestamp_ms": s.timestamp_ms,
                "confidence": s.confidence,
                "frame_path": s.frame_path,
            }
            for s in scenes
        ],
    }


# === サムネイル生成 ===

@router.get("/thumbnail/{video_id}")
async def get_thumbnail(
    video_id: str,
    timestamp_sec: float = Query(0, ge=0),
    width: int = Query(320, ge=64, le=1920),
    height: int = Query(180, ge=36, le=1080),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """サムネイルを取得"""
    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    service = VideoProcessingService()
    thumbnail_path = await service.generate_thumbnail(
        video_path,
        timestamp_sec=timestamp_sec,
        width=width,
        height=height,
    )

    return FileResponse(thumbnail_path, media_type="image/jpeg")


# === 字幕生成 ===

class SubtitleGenerationRequest(BaseModel):
    transcription_id: str
    format: SubtitleFormat = SubtitleFormat.SRT
    include_speaker_names: bool = True


@router.post("/subtitles/generate")
async def generate_subtitles(
    request: SubtitleGenerationRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """字幕ファイルを生成"""
    # 実際の実装ではDBから文字起こしセグメントを取得
    segments = [
        {
            "start_time_ms": 0,
            "end_time_ms": 5000,
            "text": "サンプルテキストです。",
            "speaker_name": "話者1" if request.include_speaker_names else None,
        },
        {
            "start_time_ms": 5000,
            "end_time_ms": 10000,
            "text": "これは字幕のサンプルです。",
            "speaker_name": "話者2" if request.include_speaker_names else None,
        },
    ]

    service = SubtitleService()

    if request.format == SubtitleFormat.SRT:
        content = service.generate_srt(segments)
        media_type = "text/plain"
    elif request.format == SubtitleFormat.VTT:
        content = service.generate_vtt(segments)
        media_type = "text/vtt"
    elif request.format == SubtitleFormat.ASS:
        content = service.generate_ass(segments)
        media_type = "text/plain"
    else:
        import json
        content = json.dumps(segments, ensure_ascii=False, indent=2)
        media_type = "application/json"

    return {
        "status": "completed",
        "format": request.format.value,
        "content": content,
    }


# === 動画+字幕統合 ===

class VideoBurnSubtitlesRequest(BaseModel):
    video_id: str
    transcription_id: str
    subtitle_format: SubtitleFormat = SubtitleFormat.ASS
    output_format: VideoFormat = VideoFormat.MP4


@router.post("/burn-subtitles")
async def burn_subtitles(
    request: VideoBurnSubtitlesRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """字幕を動画に焼き込み"""
    # 実際の実装ではDBから動画パス・セグメントを取得
    video_path = f"/tmp/{request.video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    # サンプルセグメント
    segments = [
        {
            "start_time_ms": 0,
            "end_time_ms": 5000,
            "text": "サンプルテキストです。",
        },
    ]

    service = MultimodalAnalysisService()

    # バックグラウンドで処理
    result = await service.merge_transcription_with_video(
        video_path=video_path,
        segments=segments,
        output_format=request.output_format,
        subtitle_format=request.subtitle_format,
        burn_subtitles=True,
    )

    return {
        "status": "processing",
        "video_id": request.video_id,
        "output_format": request.output_format.value,
        "subtitle_format": request.subtitle_format.value,
    }


# === 動画変換 ===

class VideoConvertRequest(BaseModel):
    video_id: str
    target_format: VideoFormat
    resolution: Optional[tuple] = None
    bitrate: Optional[str] = None


@router.post("/convert")
async def convert_video(
    request: VideoConvertRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画フォーマットを変換"""
    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{request.video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    service = VideoProcessingService()
    output_path = await service.convert_format(
        video_path,
        target_format=request.target_format,
        resolution=request.resolution,
        bitrate=request.bitrate,
    )

    return {
        "status": "completed",
        "output_path": output_path,
        "format": request.target_format.value,
    }


# === 画面内テキスト検出 (OCR) ===

@router.post("/detect-text/{video_id}")
async def detect_screen_text(
    video_id: str,
    frame_interval: float = Query(5.0, ge=1.0, le=60.0),
    language: str = Query("jpn+eng"),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """動画内の画面テキストを検出"""
    from app.services.video_processing_service import ScreenTextDetectionService

    # 実際の実装ではDBから動画パスを取得
    video_path = f"/tmp/{video_id}.mp4"

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    video_service = VideoProcessingService()
    ocr_service = ScreenTextDetectionService()

    # フレーム抽出
    frames = await video_service.extract_frames(
        video_path,
        interval_sec=frame_interval,
    )

    # OCR実行
    frames = await ocr_service.detect_text_in_video(frames, language)

    return {
        "status": "completed",
        "detected_texts": [
            {
                "timestamp_ms": f.timestamp_ms,
                "text": f.detected_text,
            }
            for f in frames
            if f.detected_text
        ],
    }
