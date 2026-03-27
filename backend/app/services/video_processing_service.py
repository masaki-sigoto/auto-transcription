"""動画処理・マルチモーダルサービス"""

import asyncio
import subprocess
import tempfile
import os
import uuid
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json


class VideoFormat(str, Enum):
    MP4 = "mp4"
    WEBM = "webm"
    MOV = "mov"
    AVI = "avi"
    MKV = "mkv"


class SubtitleFormat(str, Enum):
    SRT = "srt"
    VTT = "vtt"
    ASS = "ass"
    JSON = "json"


@dataclass
class VideoMetadata:
    duration_sec: float
    width: int
    height: int
    fps: float
    codec: str
    bitrate: int
    audio_codec: Optional[str]
    audio_channels: Optional[int]
    audio_sample_rate: Optional[int]
    file_size_bytes: int


@dataclass
class VideoFrame:
    timestamp_ms: int
    image_path: str
    description: Optional[str] = None
    detected_text: Optional[str] = None
    objects: Optional[List[str]] = None


@dataclass
class SceneChange:
    timestamp_ms: int
    confidence: float
    frame_path: str


class VideoProcessingService:
    """動画処理サービス"""

    def __init__(self, temp_dir: Optional[str] = None):
        self.temp_dir = temp_dir or tempfile.gettempdir()

    async def get_metadata(self, video_path: str) -> VideoMetadata:
        """動画のメタデータを取得"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        data = json.loads(stdout.decode())

        video_stream = next(
            (s for s in data["streams"] if s["codec_type"] == "video"),
            None
        )
        audio_stream = next(
            (s for s in data["streams"] if s["codec_type"] == "audio"),
            None
        )

        format_info = data["format"]

        return VideoMetadata(
            duration_sec=float(format_info.get("duration", 0)),
            width=int(video_stream.get("width", 0)) if video_stream else 0,
            height=int(video_stream.get("height", 0)) if video_stream else 0,
            fps=eval(video_stream.get("r_frame_rate", "0/1")) if video_stream else 0,
            codec=video_stream.get("codec_name", "") if video_stream else "",
            bitrate=int(format_info.get("bit_rate", 0)),
            audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            audio_channels=int(audio_stream.get("channels", 0)) if audio_stream else None,
            audio_sample_rate=int(audio_stream.get("sample_rate", 0)) if audio_stream else None,
            file_size_bytes=int(format_info.get("size", 0)),
        )

    async def extract_audio(
        self,
        video_path: str,
        output_format: str = "wav",
    ) -> str:
        """動画から音声を抽出"""
        output_path = os.path.join(
            self.temp_dir,
            f"audio_{uuid.uuid4().hex}.{output_format}"
        )

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vn",  # 映像を無効化
            "-acodec", "pcm_s16le" if output_format == "wav" else "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        return output_path

    async def extract_frames(
        self,
        video_path: str,
        interval_sec: float = 1.0,
        max_frames: int = 100,
    ) -> List[VideoFrame]:
        """動画からフレームを抽出"""
        output_dir = os.path.join(self.temp_dir, f"frames_{uuid.uuid4().hex}")
        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"fps=1/{interval_sec}",
            "-frames:v", str(max_frames),
            "-y",
            os.path.join(output_dir, "frame_%04d.jpg"),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        frames = []
        for i, filename in enumerate(sorted(os.listdir(output_dir))):
            if filename.endswith(".jpg"):
                frames.append(VideoFrame(
                    timestamp_ms=int(i * interval_sec * 1000),
                    image_path=os.path.join(output_dir, filename),
                ))

        return frames

    async def detect_scene_changes(
        self,
        video_path: str,
        threshold: float = 0.3,
    ) -> List[SceneChange]:
        """シーン変化を検出"""
        output_dir = os.path.join(self.temp_dir, f"scenes_{uuid.uuid4().hex}")
        os.makedirs(output_dir, exist_ok=True)

        # シーン検出用のFFmpegコマンド
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-vsync", "vfr",
            "-y",
            os.path.join(output_dir, "scene_%04d.jpg"),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        # 出力からシーン情報を解析
        scenes = []
        for i, filename in enumerate(sorted(os.listdir(output_dir))):
            if filename.endswith(".jpg"):
                scenes.append(SceneChange(
                    timestamp_ms=i * 1000,  # 簡略化
                    confidence=threshold,
                    frame_path=os.path.join(output_dir, filename),
                ))

        return scenes

    async def generate_thumbnail(
        self,
        video_path: str,
        timestamp_sec: float = 0,
        width: int = 320,
        height: int = 180,
    ) -> str:
        """サムネイルを生成"""
        output_path = os.path.join(
            self.temp_dir,
            f"thumb_{uuid.uuid4().hex}.jpg"
        )

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", str(timestamp_sec),
            "-vframes", "1",
            "-vf", f"scale={width}:{height}",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        return output_path

    async def convert_format(
        self,
        video_path: str,
        target_format: VideoFormat,
        resolution: Optional[Tuple[int, int]] = None,
        bitrate: Optional[str] = None,
    ) -> str:
        """動画フォーマットを変換"""
        output_path = os.path.join(
            self.temp_dir,
            f"converted_{uuid.uuid4().hex}.{target_format.value}"
        )

        cmd = [
            "ffmpeg",
            "-i", video_path,
        ]

        if resolution:
            cmd.extend(["-vf", f"scale={resolution[0]}:{resolution[1]}"])

        if bitrate:
            cmd.extend(["-b:v", bitrate])

        cmd.extend(["-y", output_path])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        return output_path


class SubtitleService:
    """字幕サービス"""

    def generate_srt(
        self,
        segments: List[Dict[str, Any]],
    ) -> str:
        """SRT形式の字幕を生成"""
        lines = []

        for i, seg in enumerate(segments, 1):
            start = self._ms_to_srt_time(seg["start_time_ms"])
            end = self._ms_to_srt_time(seg["end_time_ms"])
            text = seg["text"]

            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def generate_vtt(
        self,
        segments: List[Dict[str, Any]],
    ) -> str:
        """WebVTT形式の字幕を生成"""
        lines = ["WEBVTT", ""]

        for i, seg in enumerate(segments, 1):
            start = self._ms_to_vtt_time(seg["start_time_ms"])
            end = self._ms_to_vtt_time(seg["end_time_ms"])
            text = seg["text"]
            speaker = seg.get("speaker_name", "")

            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            if speaker:
                lines.append(f"<v {speaker}>{text}</v>")
            else:
                lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def generate_ass(
        self,
        segments: List[Dict[str, Any]],
        style_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """ASS形式の字幕を生成"""
        style = style_config or {}
        font_name = style.get("font_name", "Arial")
        font_size = style.get("font_size", 20)
        primary_color = style.get("primary_color", "&H00FFFFFF")
        outline_color = style.get("outline_color", "&H00000000")

        header = f"""[Script Info]
Title: Transcription
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        for seg in segments:
            start = self._ms_to_ass_time(seg["start_time_ms"])
            end = self._ms_to_ass_time(seg["end_time_ms"])
            text = seg["text"].replace("\n", "\\N")
            speaker = seg.get("speaker_name", "")

            events.append(
                f"Dialogue: 0,{start},{end},Default,{speaker},0,0,0,,{text}"
            )

        return header + "\n".join(events)

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

    def _ms_to_ass_time(self, ms: int) -> str:
        """ミリ秒をASS時間形式に変換"""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        centiseconds = (ms % 1000) // 10
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


class ScreenTextDetectionService:
    """画面内テキスト検出サービス (OCR)"""

    def __init__(self):
        self.tesseract_available = self._check_tesseract()

    def _check_tesseract(self) -> bool:
        """Tesseractが利用可能か確認"""
        try:
            subprocess.run(
                ["tesseract", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    async def detect_text_in_frame(
        self,
        image_path: str,
        language: str = "jpn+eng",
    ) -> str:
        """フレームからテキストを検出"""
        if not self.tesseract_available:
            return ""

        cmd = [
            "tesseract",
            image_path,
            "stdout",
            "-l", language,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()

        return stdout.decode().strip()

    async def detect_text_in_video(
        self,
        frames: List[VideoFrame],
        language: str = "jpn+eng",
    ) -> List[VideoFrame]:
        """動画フレームからテキストを検出"""
        for frame in frames:
            frame.detected_text = await self.detect_text_in_frame(
                frame.image_path,
                language,
            )

        return frames


class MultimodalAnalysisService:
    """マルチモーダル分析サービス"""

    def __init__(self):
        self.video_service = VideoProcessingService()
        self.subtitle_service = SubtitleService()
        self.ocr_service = ScreenTextDetectionService()

    async def process_video(
        self,
        video_path: str,
        extract_text: bool = True,
        detect_scenes: bool = True,
        frame_interval: float = 5.0,
    ) -> Dict[str, Any]:
        """動画を処理して情報を抽出"""
        # メタデータ取得
        metadata = await self.video_service.get_metadata(video_path)

        # 音声抽出
        audio_path = await self.video_service.extract_audio(video_path)

        result = {
            "metadata": {
                "duration_sec": metadata.duration_sec,
                "resolution": f"{metadata.width}x{metadata.height}",
                "fps": metadata.fps,
                "codec": metadata.codec,
            },
            "audio_path": audio_path,
            "frames": [],
            "scenes": [],
            "detected_texts": [],
        }

        # フレーム抽出
        frames = await self.video_service.extract_frames(
            video_path,
            interval_sec=frame_interval,
        )
        result["frames"] = [
            {
                "timestamp_ms": f.timestamp_ms,
                "image_path": f.image_path,
            }
            for f in frames
        ]

        # OCRテキスト検出
        if extract_text and self.ocr_service.tesseract_available:
            frames = await self.ocr_service.detect_text_in_video(frames)
            result["detected_texts"] = [
                {
                    "timestamp_ms": f.timestamp_ms,
                    "text": f.detected_text,
                }
                for f in frames
                if f.detected_text
            ]

        # シーン検出
        if detect_scenes:
            scenes = await self.video_service.detect_scene_changes(video_path)
            result["scenes"] = [
                {
                    "timestamp_ms": s.timestamp_ms,
                    "confidence": s.confidence,
                    "frame_path": s.frame_path,
                }
                for s in scenes
            ]

        return result

    async def merge_transcription_with_video(
        self,
        video_path: str,
        segments: List[Dict[str, Any]],
        output_format: VideoFormat = VideoFormat.MP4,
        subtitle_format: SubtitleFormat = SubtitleFormat.SRT,
        burn_subtitles: bool = False,
    ) -> Dict[str, str]:
        """文字起こしを動画と統合"""
        # 字幕ファイル生成
        if subtitle_format == SubtitleFormat.SRT:
            subtitle_content = self.subtitle_service.generate_srt(segments)
        elif subtitle_format == SubtitleFormat.VTT:
            subtitle_content = self.subtitle_service.generate_vtt(segments)
        elif subtitle_format == SubtitleFormat.ASS:
            subtitle_content = self.subtitle_service.generate_ass(segments)
        else:
            subtitle_content = json.dumps(segments, ensure_ascii=False, indent=2)

        # 字幕ファイルを保存
        subtitle_path = os.path.join(
            tempfile.gettempdir(),
            f"subtitle_{uuid.uuid4().hex}.{subtitle_format.value}"
        )
        with open(subtitle_path, "w", encoding="utf-8") as f:
            f.write(subtitle_content)

        result = {
            "subtitle_path": subtitle_path,
            "subtitle_content": subtitle_content,
        }

        # 字幕を焼き込み
        if burn_subtitles:
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"subtitled_{uuid.uuid4().hex}.{output_format.value}"
            )

            if subtitle_format == SubtitleFormat.ASS:
                vf = f"ass={subtitle_path}"
            else:
                vf = f"subtitles={subtitle_path}"

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", vf,
                "-c:a", "copy",
                "-y",
                output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            result["video_with_subtitles"] = output_path

        return result
