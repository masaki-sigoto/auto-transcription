import os
import tempfile
from dataclasses import dataclass
from typing import Optional
import torch


@dataclass
class SpeakerSegment:
    """話者セグメント"""
    start_time_ms: int
    end_time_ms: int
    speaker_id: str
    confidence: float | None = None


class SpeakerDiarization:
    """話者識別サービス（pyannote.audio）"""

    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token or os.getenv("HF_AUTH_TOKEN")
        self.pipeline = None

    def _load_pipeline(self):
        """パイプラインの遅延読み込み"""
        if self.pipeline is None:
            try:
                from pyannote.audio import Pipeline

                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.auth_token,
                )

                # GPU利用可能ならGPUを使用
                if torch.cuda.is_available():
                    self.pipeline.to(torch.device("cuda"))

            except ImportError:
                raise RuntimeError("pyannote.audio is not installed")
            except Exception as e:
                raise RuntimeError(f"Failed to load diarization pipeline: {e}")

    async def diarize(
        self,
        audio_path: str,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[SpeakerSegment]:
        """
        音声ファイルから話者を識別

        Args:
            audio_path: 音声ファイルパス
            num_speakers: 話者数（既知の場合）
            min_speakers: 最小話者数
            max_speakers: 最大話者数

        Returns:
            話者セグメントのリスト
        """
        self._load_pipeline()

        # パイプラインパラメータ
        params = {}
        if num_speakers is not None:
            params["num_speakers"] = num_speakers
        if min_speakers is not None:
            params["min_speakers"] = min_speakers
        if max_speakers is not None:
            params["max_speakers"] = max_speakers

        # 話者識別実行
        diarization = self.pipeline(audio_path, **params)

        # 結果をセグメントに変換
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                SpeakerSegment(
                    start_time_ms=int(turn.start * 1000),
                    end_time_ms=int(turn.end * 1000),
                    speaker_id=speaker,
                )
            )

        return segments

    def merge_with_transcription(
        self,
        transcription_segments: list[dict],
        speaker_segments: list[SpeakerSegment],
    ) -> list[dict]:
        """
        文字起こしセグメントに話者情報をマージ

        Args:
            transcription_segments: 文字起こしセグメント
            speaker_segments: 話者セグメント

        Returns:
            話者情報付き文字起こしセグメント
        """
        result = []

        for trans_seg in transcription_segments:
            trans_start = trans_seg["start_time_ms"]
            trans_end = trans_seg["end_time_ms"]
            trans_mid = (trans_start + trans_end) / 2

            # 最も重複が大きい話者を見つける
            best_speaker = None
            best_overlap = 0

            for speaker_seg in speaker_segments:
                # 重複計算
                overlap_start = max(trans_start, speaker_seg.start_time_ms)
                overlap_end = min(trans_end, speaker_seg.end_time_ms)
                overlap = max(0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker_seg.speaker_id

            result.append({
                **trans_seg,
                "speaker_id": best_speaker,
            })

        return result


class SimpleSpeakerDiarization:
    """
    シンプルな話者識別（pyannote不要版）
    音声特徴量に基づくクラスタリング
    """

    def __init__(self):
        self.embeddings = []

    async def diarize(
        self,
        audio_path: str,
        num_speakers: int = 2,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[SpeakerSegment]:
        """
        シンプルな話者識別

        Args:
            audio_path: 音声ファイルパス
            num_speakers: 想定話者数
            min_speakers: 最小話者数（num_speakersより優先）
            max_speakers: 最大話者数（num_speakersより優先）

        Returns:
            話者セグメントのリスト
        """
        try:
            import librosa
            import numpy as np
            from sklearn.cluster import AgglomerativeClustering

            # 音声読み込み
            y, sr = librosa.load(audio_path, sr=16000)

            # 音声区間検出（より細かく）
            intervals = librosa.effects.split(y, top_db=25)

            if len(intervals) == 0:
                return []

            # 各区間のMFCC特徴量を計算
            features = []
            for start, end in intervals:
                segment = y[start:end]
                if len(segment) < sr * 0.3:  # 0.3秒未満はスキップ
                    continue

                # より多くの特徴量を抽出
                mfcc = librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=20)
                delta_mfcc = librosa.feature.delta(mfcc)

                # 平均と分散を特徴量として使用
                feature = np.concatenate([
                    np.mean(mfcc, axis=1),
                    np.std(mfcc, axis=1),
                    np.mean(delta_mfcc, axis=1),
                ])
                features.append({
                    "start_ms": int(start / sr * 1000),
                    "end_ms": int(end / sr * 1000),
                    "feature": feature,
                })

            if len(features) == 0:
                return []

            if len(features) == 1:
                # セグメントが1つの場合は単一話者
                return [
                    SpeakerSegment(
                        start_time_ms=features[0]["start_ms"],
                        end_time_ms=features[0]["end_ms"],
                        speaker_id="SPEAKER_0",
                    )
                ]

            # 話者数の決定
            target_speakers = num_speakers
            if min_speakers is not None and max_speakers is not None:
                # 自動推定：シルエットスコアで最適なクラスタ数を決定
                from sklearn.metrics import silhouette_score

                X = np.array([f["feature"] for f in features])
                best_score = -1
                best_n = min_speakers

                for n in range(min_speakers, min(max_speakers + 1, len(features))):
                    try:
                        clustering = AgglomerativeClustering(
                            n_clusters=n,
                            metric="cosine",
                            linkage="average",
                        )
                        labels = clustering.fit_predict(X)

                        if len(set(labels)) > 1:
                            score = silhouette_score(X, labels, metric="cosine")
                            if score > best_score:
                                best_score = score
                                best_n = n
                    except Exception:
                        continue

                target_speakers = best_n

            # クラスタリング
            X = np.array([f["feature"] for f in features])
            n_clusters = min(target_speakers, len(features))

            clustering = AgglomerativeClustering(
                n_clusters=n_clusters,
                metric="cosine",
                linkage="average",
            )
            labels = clustering.fit_predict(X)

            # 結果を構築
            segments = []
            for i, f in enumerate(features):
                segments.append(
                    SpeakerSegment(
                        start_time_ms=f["start_ms"],
                        end_time_ms=f["end_ms"],
                        speaker_id=f"SPEAKER_{labels[i]}",
                    )
                )

            # 連続する同一話者セグメントをマージ
            merged_segments = self._merge_consecutive_segments(segments)

            return merged_segments

        except ImportError as e:
            raise RuntimeError(f"Required library not installed: {e}")

    def _merge_consecutive_segments(
        self,
        segments: list[SpeakerSegment],
        gap_threshold_ms: int = 500,
    ) -> list[SpeakerSegment]:
        """連続する同一話者のセグメントをマージ"""
        if not segments:
            return []

        merged = []
        current = segments[0]

        for seg in segments[1:]:
            # 同じ話者で、間隔が短い場合はマージ
            if (seg.speaker_id == current.speaker_id and
                seg.start_time_ms - current.end_time_ms <= gap_threshold_ms):
                current = SpeakerSegment(
                    start_time_ms=current.start_time_ms,
                    end_time_ms=seg.end_time_ms,
                    speaker_id=current.speaker_id,
                )
            else:
                merged.append(current)
                current = seg

        merged.append(current)
        return merged


def get_diarization_service(use_pyannote: bool = False) -> SpeakerDiarization | SimpleSpeakerDiarization:
    """話者識別サービスを取得"""
    if use_pyannote:
        return SpeakerDiarization()
    return SimpleSpeakerDiarization()
