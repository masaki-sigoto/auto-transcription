"""高度な音声処理サービス"""

import os
import tempfile
import subprocess
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
import numpy as np
from pydantic import BaseModel


class AudioQuality(str, Enum):
    """音声品質レベル"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    VERY_POOR = "very_poor"


@dataclass
class AudioAnalysisResult:
    """音声分析結果"""
    quality: AudioQuality
    snr_db: float  # Signal-to-Noise Ratio
    loudness_lufs: float
    clipping_percentage: float
    silence_percentage: float
    sample_rate: int
    channels: int
    duration_seconds: float
    issues: List[str]
    recommendations: List[str]


class NoiseProfile(BaseModel):
    """ノイズプロファイル"""
    type: str  # background, hum, hiss, echo
    intensity: float  # 0-1
    frequency_range: Tuple[int, int]


class AudioProcessingService:
    """音声処理サービス"""

    def __init__(self):
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"

    async def analyze_audio(self, file_path: str) -> AudioAnalysisResult:
        """音声品質を分析"""
        import soundfile as sf

        # 音声ファイル読み込み
        data, sample_rate = sf.read(file_path)

        # モノラル変換
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        # 基本情報
        duration = len(data) / sample_rate
        channels = 1 if len(data.shape) == 1 else data.shape[1]

        # SNR計算
        snr_db = self._calculate_snr(data)

        # ラウドネス計算 (簡易版)
        rms = np.sqrt(np.mean(data ** 2))
        loudness_lufs = 20 * np.log10(rms + 1e-10) - 23  # 概算LUFS

        # クリッピング検出
        clipping_threshold = 0.99
        clipping_samples = np.sum(np.abs(data) > clipping_threshold)
        clipping_percentage = (clipping_samples / len(data)) * 100

        # 無音検出
        silence_threshold = 0.01
        silence_samples = np.sum(np.abs(data) < silence_threshold)
        silence_percentage = (silence_samples / len(data)) * 100

        # 品質判定
        quality, issues, recommendations = self._assess_quality(
            snr_db, loudness_lufs, clipping_percentage, silence_percentage
        )

        return AudioAnalysisResult(
            quality=quality,
            snr_db=snr_db,
            loudness_lufs=loudness_lufs,
            clipping_percentage=clipping_percentage,
            silence_percentage=silence_percentage,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration,
            issues=issues,
            recommendations=recommendations,
        )

    def _calculate_snr(self, data: np.ndarray) -> float:
        """SNR（信号対雑音比）を計算"""
        # 簡易的なSNR計算
        # 信号パワー
        signal_power = np.mean(data ** 2)

        # ノイズ推定（最も静かな部分）
        frame_size = int(len(data) * 0.01)  # 1%のフレーム
        min_power = float('inf')

        for i in range(0, len(data) - frame_size, frame_size):
            frame = data[i:i + frame_size]
            power = np.mean(frame ** 2)
            if power < min_power and power > 1e-10:
                min_power = power

        noise_power = min_power if min_power != float('inf') else 1e-10

        # SNR計算
        snr = 10 * np.log10(signal_power / noise_power)
        return float(snr)

    def _assess_quality(
        self,
        snr_db: float,
        loudness_lufs: float,
        clipping_percentage: float,
        silence_percentage: float,
    ) -> Tuple[AudioQuality, List[str], List[str]]:
        """品質を評価"""
        issues = []
        recommendations = []
        score = 100

        # SNR評価
        if snr_db < 10:
            issues.append("ノイズレベルが非常に高い")
            recommendations.append("静かな環境で録音してください")
            score -= 40
        elif snr_db < 20:
            issues.append("ノイズレベルが高い")
            recommendations.append("マイクを口に近づけてください")
            score -= 20
        elif snr_db < 30:
            score -= 10

        # ラウドネス評価
        if loudness_lufs < -30:
            issues.append("音量が小さすぎる")
            recommendations.append("マイクの入力レベルを上げてください")
            score -= 20
        elif loudness_lufs > -10:
            issues.append("音量が大きすぎる")
            recommendations.append("マイクの入力レベルを下げてください")
            score -= 15

        # クリッピング評価
        if clipping_percentage > 1:
            issues.append("音割れが検出されました")
            recommendations.append("録音レベルを下げてください")
            score -= 25
        elif clipping_percentage > 0.1:
            issues.append("軽微な音割れがあります")
            score -= 10

        # 無音評価
        if silence_percentage > 50:
            issues.append("無音部分が多い")
            recommendations.append("録音時間を確認してください")
            score -= 15

        # 総合評価
        if score >= 90:
            quality = AudioQuality.EXCELLENT
        elif score >= 70:
            quality = AudioQuality.GOOD
        elif score >= 50:
            quality = AudioQuality.FAIR
        elif score >= 30:
            quality = AudioQuality.POOR
        else:
            quality = AudioQuality.VERY_POOR

        return quality, issues, recommendations

    async def remove_noise(
        self,
        input_path: str,
        output_path: str,
        noise_reduction_level: float = 0.5,
    ) -> str:
        """ノイズ除去"""
        # FFmpegのanlmdn（Non-Local Means Denoiser）フィルタを使用
        strength = int(noise_reduction_level * 10)

        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-af", f"anlmdn=s={strength}:p=0.002:r=0.002:m=15",
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Noise removal failed: {process.stderr}")

        return output_path

    async def enhance_voice(
        self,
        input_path: str,
        output_path: str,
    ) -> str:
        """音声強調（話者の声をクリアに）"""
        # ハイパスフィルタ + コンプレッサー + EQ
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-af", (
                "highpass=f=80,"  # 80Hz以下をカット
                "lowpass=f=8000,"  # 8kHz以上をカット
                "equalizer=f=300:t=q:w=1:g=2,"  # 低域強調
                "equalizer=f=3000:t=q:w=1:g=3,"  # 高域強調（明瞭度）
                "compand=attacks=0.3:decays=0.8:points=-80/-80|-45/-15|-27/-9|0/-7|20/-7:soft-knee=6:gain=5,"
                "loudnorm=I=-16:TP=-1.5:LRA=11"  # ラウドネス正規化
            ),
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Voice enhancement failed: {process.stderr}")

        return output_path

    async def remove_echo(
        self,
        input_path: str,
        output_path: str,
    ) -> str:
        """エコー除去"""
        # FFmpegのaechoフィルタの逆位相を使用（簡易版）
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-af", "aecho=0.8:0.88:60:0.4",
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Echo removal failed: {process.stderr}")

        return output_path

    async def normalize_audio(
        self,
        input_path: str,
        output_path: str,
        target_lufs: float = -16.0,
    ) -> str:
        """音量正規化"""
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Normalization failed: {process.stderr}")

        return output_path

    async def convert_sample_rate(
        self,
        input_path: str,
        output_path: str,
        target_sample_rate: int = 16000,
    ) -> str:
        """サンプルレート変換"""
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-ar", str(target_sample_rate),
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Sample rate conversion failed: {process.stderr}")

        return output_path

    async def process_multi_channel(
        self,
        input_path: str,
        output_path: str,
        channel_mode: str = "mix",  # mix, left, right, best
    ) -> str:
        """マルチチャンネル処理"""
        if channel_mode == "mix":
            af_filter = "pan=mono|c0=0.5*c0+0.5*c1"
        elif channel_mode == "left":
            af_filter = "pan=mono|c0=c0"
        elif channel_mode == "right":
            af_filter = "pan=mono|c0=c1"
        else:  # best - 自動選択
            af_filter = "pan=mono|c0=0.5*c0+0.5*c1"

        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-af", af_filter,
            "-y",
            output_path,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise RuntimeError(f"Multi-channel processing failed: {process.stderr}")

        return output_path

    async def full_enhancement_pipeline(
        self,
        input_path: str,
        output_path: str,
        noise_reduction: bool = True,
        voice_enhancement: bool = True,
        normalize: bool = True,
    ) -> Tuple[str, AudioAnalysisResult]:
        """完全な音声強調パイプライン"""
        # 一時ファイル用ディレクトリ
        temp_dir = tempfile.mkdtemp()
        current_path = input_path

        try:
            # 1. 初期分析
            initial_analysis = await self.analyze_audio(input_path)

            # 2. サンプルレート変換（必要な場合）
            if initial_analysis.sample_rate != 16000:
                temp_path = os.path.join(temp_dir, "sr_converted.wav")
                await self.convert_sample_rate(current_path, temp_path, 16000)
                current_path = temp_path

            # 3. ノイズ除去
            if noise_reduction and initial_analysis.snr_db < 30:
                temp_path = os.path.join(temp_dir, "denoised.wav")
                level = min(1.0, max(0.3, (30 - initial_analysis.snr_db) / 30))
                await self.remove_noise(current_path, temp_path, level)
                current_path = temp_path

            # 4. 音声強調
            if voice_enhancement:
                temp_path = os.path.join(temp_dir, "enhanced.wav")
                await self.enhance_voice(current_path, temp_path)
                current_path = temp_path

            # 5. 正規化
            if normalize:
                await self.normalize_audio(current_path, output_path)
            else:
                # コピー
                subprocess.run(["cp", current_path, output_path])

            # 6. 最終分析
            final_analysis = await self.analyze_audio(output_path)

            return output_path, final_analysis

        finally:
            # 一時ファイル削除
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class AudioSegmentationService:
    """音声セグメンテーションサービス"""

    async def detect_speech_segments(
        self,
        file_path: str,
        min_speech_duration: float = 0.5,
        min_silence_duration: float = 0.3,
    ) -> List[Tuple[float, float]]:
        """音声区間を検出"""
        import soundfile as sf

        data, sample_rate = sf.read(file_path)

        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        # エネルギーベースのVAD
        frame_size = int(sample_rate * 0.025)  # 25ms
        hop_size = int(sample_rate * 0.010)  # 10ms

        energies = []
        for i in range(0, len(data) - frame_size, hop_size):
            frame = data[i:i + frame_size]
            energy = np.sum(frame ** 2) / frame_size
            energies.append(energy)

        energies = np.array(energies)

        # 閾値計算（適応的）
        threshold = np.percentile(energies, 30) * 2

        # 音声区間検出
        is_speech = energies > threshold

        # セグメント化
        segments = []
        in_speech = False
        start_frame = 0

        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                start_frame = i
                in_speech = True
            elif not speech and in_speech:
                end_frame = i
                start_time = start_frame * hop_size / sample_rate
                end_time = end_frame * hop_size / sample_rate

                if end_time - start_time >= min_speech_duration:
                    segments.append((start_time, end_time))

                in_speech = False

        # 最後のセグメント
        if in_speech:
            end_time = len(is_speech) * hop_size / sample_rate
            start_time = start_frame * hop_size / sample_rate
            if end_time - start_time >= min_speech_duration:
                segments.append((start_time, end_time))

        # 近接セグメントのマージ
        merged_segments = []
        for segment in segments:
            if merged_segments and segment[0] - merged_segments[-1][1] < min_silence_duration:
                merged_segments[-1] = (merged_segments[-1][0], segment[1])
            else:
                merged_segments.append(segment)

        return merged_segments

    async def split_by_silence(
        self,
        file_path: str,
        output_dir: str,
        min_silence_duration: float = 1.0,
        silence_threshold_db: float = -40,
    ) -> List[str]:
        """無音部分で分割"""
        segments = await self.detect_speech_segments(
            file_path,
            min_silence_duration=min_silence_duration,
        )

        output_files = []
        for i, (start, end) in enumerate(segments):
            output_path = os.path.join(output_dir, f"segment_{i:04d}.wav")

            cmd = [
                "ffmpeg",
                "-i", file_path,
                "-ss", str(start),
                "-to", str(end),
                "-y",
                output_path,
            ]

            subprocess.run(cmd, capture_output=True)
            output_files.append(output_path)

        return output_files
