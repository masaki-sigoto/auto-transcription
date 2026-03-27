import os
import tempfile
import subprocess
from pathlib import Path


class AudioProcessor:
    """音声ファイルの前処理を担当するクラス"""

    SUPPORTED_FORMATS = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm"]
    TARGET_SAMPLE_RATE = 16000
    TARGET_CHANNELS = 1

    def __init__(self):
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """FFmpegの存在確認"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg is not installed or not in PATH")

    def normalize_audio(self, input_path: str, output_path: str | None = None) -> str:
        """
        音声ファイルを正規化（WAV 16kHz mono）

        Args:
            input_path: 入力ファイルパス
            output_path: 出力ファイルパス（Noneの場合は一時ファイル）

        Returns:
            正規化された音声ファイルのパス
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-ar", str(self.TARGET_SAMPLE_RATE),
            "-ac", str(self.TARGET_CHANNELS),
            "-c:a", "pcm_s16le",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr}")

        return output_path

    def get_duration(self, file_path: str) -> float:
        """音声ファイルの長さを秒で取得"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe error: {result.stderr}")

        return float(result.stdout.strip())

    def split_audio(
        self,
        input_path: str,
        chunk_duration_sec: int = 30,
        output_dir: str | None = None,
    ) -> list[str]:
        """
        音声ファイルをチャンクに分割

        Args:
            input_path: 入力ファイルパス
            chunk_duration_sec: チャンクの長さ（秒）
            output_dir: 出力ディレクトリ

        Returns:
            分割されたファイルパスのリスト
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp()

        total_duration = self.get_duration(input_path)
        chunk_paths = []
        chunk_index = 0
        start_time = 0.0

        while start_time < total_duration:
            output_path = os.path.join(output_dir, f"chunk_{chunk_index:04d}.wav")

            cmd = [
                "ffmpeg",
                "-y",
                "-i", input_path,
                "-ss", str(start_time),
                "-t", str(chunk_duration_sec),
                "-c:a", "pcm_s16le",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {result.stderr}")

            chunk_paths.append(output_path)
            start_time += chunk_duration_sec
            chunk_index += 1

        return chunk_paths

    def detect_silence(
        self,
        file_path: str,
        silence_threshold: float = -40,
        min_silence_duration: float = 0.5,
    ) -> list[tuple[float, float]]:
        """
        無音区間を検出

        Args:
            file_path: 音声ファイルパス
            silence_threshold: 無音と判定する閾値（dB）
            min_silence_duration: 最小無音区間（秒）

        Returns:
            無音区間のリスト [(start, end), ...]
        """
        cmd = [
            "ffmpeg",
            "-i", file_path,
            "-af", f"silencedetect=noise={silence_threshold}dB:d={min_silence_duration}",
            "-f", "null",
            "-",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        stderr = result.stderr

        silences = []
        lines = stderr.split("\n")
        start = None

        for line in lines:
            if "silence_start:" in line:
                start = float(line.split("silence_start:")[1].strip().split()[0])
            elif "silence_end:" in line and start is not None:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                silences.append((start, end))
                start = None

        return silences
