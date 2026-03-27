"""高度な話者分析・感情分析サービス"""

import os
import uuid
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import math


class Emotion(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    CONTEMPT = "contempt"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ToneType(str, Enum):
    FORMAL = "formal"
    INFORMAL = "informal"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    ASSERTIVE = "assertive"
    TENTATIVE = "tentative"


@dataclass
class EmotionScore:
    """感情スコア"""
    emotion: Emotion
    score: float  # 0.0 - 1.0
    confidence: float


@dataclass
class SentimentResult:
    """感情分析結果"""
    sentiment: Sentiment
    score: float  # -1.0 (negative) to 1.0 (positive)
    confidence: float
    keywords: List[str] = field(default_factory=list)


@dataclass
class ToneAnalysis:
    """トーン分析"""
    primary_tone: ToneType
    tones: Dict[ToneType, float]
    speech_rate: float  # words per minute
    pitch_variation: float  # 0.0 - 1.0
    volume_level: float  # 0.0 - 1.0
    pause_frequency: float  # pauses per minute


@dataclass
class SpeakerProfile:
    """話者プロファイル"""
    speaker_id: str
    name: Optional[str] = None
    total_speaking_time_ms: int = 0
    segment_count: int = 0
    average_segment_length_ms: float = 0.0
    word_count: int = 0
    average_words_per_segment: float = 0.0
    dominant_emotion: Optional[Emotion] = None
    average_sentiment: float = 0.0
    tone_profile: Optional[ToneAnalysis] = None


@dataclass
class InteractionPattern:
    """対話パターン"""
    speaker_a: str
    speaker_b: str
    interaction_count: int
    average_response_time_ms: float
    overlap_count: int
    interruption_count: int


@dataclass
class MeetingAtmosphere:
    """会議雰囲気"""
    overall_sentiment: float  # -1.0 to 1.0
    engagement_score: float  # 0.0 to 1.0
    collaboration_score: float  # 0.0 to 1.0
    tension_level: float  # 0.0 to 1.0
    energy_level: float  # 0.0 to 1.0
    dominant_emotions: List[Tuple[Emotion, float]]
    highlights: List[Dict[str, Any]]
    concerns: List[Dict[str, Any]]


class EmotionAnalyzer:
    """感情分析エンジン"""

    def __init__(self):
        # 感情キーワード辞書（日本語）
        self._emotion_keywords = {
            Emotion.HAPPY: ["嬉しい", "楽しい", "素晴らしい", "最高", "ありがとう", "良い", "成功"],
            Emotion.SAD: ["悲しい", "残念", "申し訳", "困った", "辛い", "失敗"],
            Emotion.ANGRY: ["怒り", "腹立たしい", "許せない", "問題", "ひどい", "最悪"],
            Emotion.FEARFUL: ["心配", "不安", "怖い", "リスク", "危険", "懸念"],
            Emotion.SURPRISED: ["驚き", "びっくり", "まさか", "予想外", "意外"],
        }

        self._sentiment_keywords = {
            "positive": ["良い", "素晴らしい", "成功", "達成", "改善", "順調", "期待"],
            "negative": ["悪い", "問題", "失敗", "遅延", "困難", "課題", "リスク"],
        }

    async def analyze_segment(
        self,
        text: str,
        audio_features: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """セグメントを分析"""
        # テキストベースの感情分析
        emotions = await self._analyze_text_emotions(text)

        # センチメント分析
        sentiment = await self._analyze_sentiment(text)

        # 音声特徴がある場合は統合
        if audio_features:
            emotions = self._integrate_audio_emotions(emotions, audio_features)

        return {
            "emotions": emotions,
            "sentiment": sentiment,
            "primary_emotion": max(emotions, key=lambda e: e.score) if emotions else None,
        }

    async def _analyze_text_emotions(self, text: str) -> List[EmotionScore]:
        """テキストから感情を分析"""
        emotions = []

        for emotion, keywords in self._emotion_keywords.items():
            score = sum(1 for kw in keywords if kw in text) / len(keywords)
            if score > 0:
                emotions.append(EmotionScore(
                    emotion=emotion,
                    score=min(score * 2, 1.0),  # スケール調整
                    confidence=0.7,
                ))

        # デフォルトでニュートラルを追加
        if not emotions:
            emotions.append(EmotionScore(
                emotion=Emotion.NEUTRAL,
                score=0.8,
                confidence=0.9,
            ))

        return emotions

    async def _analyze_sentiment(self, text: str) -> SentimentResult:
        """センチメント分析"""
        positive_count = sum(1 for kw in self._sentiment_keywords["positive"] if kw in text)
        negative_count = sum(1 for kw in self._sentiment_keywords["negative"] if kw in text)

        total = positive_count + negative_count
        if total == 0:
            return SentimentResult(
                sentiment=Sentiment.NEUTRAL,
                score=0.0,
                confidence=0.8,
            )

        score = (positive_count - negative_count) / total

        if score > 0.2:
            sentiment = Sentiment.POSITIVE
        elif score < -0.2:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL

        return SentimentResult(
            sentiment=sentiment,
            score=score,
            confidence=0.75,
        )

    def _integrate_audio_emotions(
        self,
        text_emotions: List[EmotionScore],
        audio_features: Dict[str, float],
    ) -> List[EmotionScore]:
        """音声特徴を統合"""
        # 音声から追加の感情手がかりを抽出
        pitch = audio_features.get("pitch", 0.5)
        energy = audio_features.get("energy", 0.5)
        speech_rate = audio_features.get("speech_rate", 1.0)

        # 高いピッチと高いエネルギー → 興奮/喜び
        if pitch > 0.7 and energy > 0.7:
            for e in text_emotions:
                if e.emotion == Emotion.HAPPY:
                    e.score = min(e.score + 0.2, 1.0)

        # 低いエネルギーと遅い話速 → 悲しみ
        if energy < 0.3 and speech_rate < 0.7:
            for e in text_emotions:
                if e.emotion == Emotion.SAD:
                    e.score = min(e.score + 0.2, 1.0)

        return text_emotions


class ToneAnalyzer:
    """トーン分析エンジン"""

    async def analyze_tone(
        self,
        text: str,
        audio_features: Optional[Dict[str, float]] = None,
    ) -> ToneAnalysis:
        """トーンを分析"""
        # テキストからトーンを推測
        tones = await self._analyze_text_tone(text)

        # 音声特徴からスピーチ特性を抽出
        speech_rate = audio_features.get("speech_rate", 120) if audio_features else 120
        pitch_variation = audio_features.get("pitch_variation", 0.5) if audio_features else 0.5
        volume_level = audio_features.get("volume", 0.5) if audio_features else 0.5
        pause_frequency = audio_features.get("pause_frequency", 5) if audio_features else 5

        primary_tone = max(tones.items(), key=lambda x: x[1])[0]

        return ToneAnalysis(
            primary_tone=primary_tone,
            tones=tones,
            speech_rate=speech_rate,
            pitch_variation=pitch_variation,
            volume_level=volume_level,
            pause_frequency=pause_frequency,
        )

    async def _analyze_text_tone(self, text: str) -> Dict[ToneType, float]:
        """テキストからトーンを分析"""
        tones = {
            ToneType.FORMAL: 0.0,
            ToneType.INFORMAL: 0.0,
            ToneType.PROFESSIONAL: 0.0,
            ToneType.CASUAL: 0.0,
            ToneType.ASSERTIVE: 0.0,
            ToneType.TENTATIVE: 0.0,
        }

        # フォーマル指標
        formal_markers = ["です", "ます", "ございます", "いたします", "させていただき"]
        informal_markers = ["だよ", "じゃん", "だね", "かな", "っす"]
        assertive_markers = ["必ず", "絶対", "間違いなく", "確実に", "べき"]
        tentative_markers = ["かもしれ", "思います", "おそらく", "多分", "でしょうか"]

        for marker in formal_markers:
            if marker in text:
                tones[ToneType.FORMAL] += 0.2
                tones[ToneType.PROFESSIONAL] += 0.1

        for marker in informal_markers:
            if marker in text:
                tones[ToneType.INFORMAL] += 0.2
                tones[ToneType.CASUAL] += 0.1

        for marker in assertive_markers:
            if marker in text:
                tones[ToneType.ASSERTIVE] += 0.2

        for marker in tentative_markers:
            if marker in text:
                tones[ToneType.TENTATIVE] += 0.2

        # 正規化
        total = sum(tones.values())
        if total > 0:
            tones = {k: v / total for k, v in tones.items()}
        else:
            tones[ToneType.NEUTRAL] = 1.0 if hasattr(ToneType, 'NEUTRAL') else 0.0
            tones[ToneType.PROFESSIONAL] = 0.5

        return tones


class SpeakerAnalyzer:
    """話者分析エンジン"""

    def __init__(self):
        self._profiles: Dict[str, SpeakerProfile] = {}
        self._interactions: List[InteractionPattern] = []

    async def analyze_speaker(
        self,
        speaker_id: str,
        segments: List[Dict[str, Any]],
    ) -> SpeakerProfile:
        """話者を分析"""
        if speaker_id not in self._profiles:
            self._profiles[speaker_id] = SpeakerProfile(speaker_id=speaker_id)

        profile = self._profiles[speaker_id]

        # 統計を計算
        speaker_segments = [s for s in segments if s.get("speaker_id") == speaker_id]

        if speaker_segments:
            profile.segment_count = len(speaker_segments)
            profile.total_speaking_time_ms = sum(
                s.get("end_time_ms", 0) - s.get("start_time_ms", 0)
                for s in speaker_segments
            )
            profile.average_segment_length_ms = (
                profile.total_speaking_time_ms / profile.segment_count
            )

            # ワードカウント
            all_text = " ".join(s.get("text", "") for s in speaker_segments)
            profile.word_count = len(all_text.split())
            profile.average_words_per_segment = profile.word_count / profile.segment_count

        return profile

    async def analyze_interactions(
        self,
        segments: List[Dict[str, Any]],
    ) -> List[InteractionPattern]:
        """対話パターンを分析"""
        interactions = {}

        for i in range(1, len(segments)):
            prev_speaker = segments[i - 1].get("speaker_id")
            curr_speaker = segments[i].get("speaker_id")

            if prev_speaker and curr_speaker and prev_speaker != curr_speaker:
                key = tuple(sorted([prev_speaker, curr_speaker]))
                if key not in interactions:
                    interactions[key] = {
                        "count": 0,
                        "response_times": [],
                        "overlaps": 0,
                        "interruptions": 0,
                    }

                interactions[key]["count"] += 1

                # レスポンスタイムを計算
                prev_end = segments[i - 1].get("end_time_ms", 0)
                curr_start = segments[i].get("start_time_ms", 0)
                response_time = curr_start - prev_end

                if response_time < 0:
                    interactions[key]["overlaps"] += 1
                elif response_time < 200:  # 200ms未満は割り込みの可能性
                    interactions[key]["interruptions"] += 1
                else:
                    interactions[key]["response_times"].append(response_time)

        # InteractionPatternに変換
        result = []
        for (speaker_a, speaker_b), data in interactions.items():
            avg_response = (
                sum(data["response_times"]) / len(data["response_times"])
                if data["response_times"] else 0
            )
            result.append(InteractionPattern(
                speaker_a=speaker_a,
                speaker_b=speaker_b,
                interaction_count=data["count"],
                average_response_time_ms=avg_response,
                overlap_count=data["overlaps"],
                interruption_count=data["interruptions"],
            ))

        self._interactions = result
        return result


class MeetingAnalyzer:
    """会議分析エンジン"""

    def __init__(self):
        self.emotion_analyzer = EmotionAnalyzer()
        self.tone_analyzer = ToneAnalyzer()
        self.speaker_analyzer = SpeakerAnalyzer()

    async def analyze_meeting(
        self,
        segments: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MeetingAtmosphere:
        """会議全体を分析"""
        all_sentiments = []
        all_emotions = []
        highlights = []
        concerns = []

        for i, segment in enumerate(segments):
            text = segment.get("text", "")
            analysis = await self.emotion_analyzer.analyze_segment(text)

            sentiment = analysis["sentiment"]
            all_sentiments.append(sentiment.score)

            for emotion in analysis["emotions"]:
                all_emotions.append((emotion.emotion, emotion.score))

            # ハイライトを検出
            if sentiment.score > 0.5:
                highlights.append({
                    "segment_index": i,
                    "text": text[:100],
                    "reason": "positive_sentiment",
                    "score": sentiment.score,
                })

            # 懸念を検出
            if sentiment.score < -0.3:
                concerns.append({
                    "segment_index": i,
                    "text": text[:100],
                    "reason": "negative_sentiment",
                    "score": sentiment.score,
                })

        # 全体スコアを計算
        overall_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 0

        # 感情の集計
        emotion_totals: Dict[Emotion, float] = {}
        for emotion, score in all_emotions:
            if emotion not in emotion_totals:
                emotion_totals[emotion] = 0
            emotion_totals[emotion] += score

        dominant_emotions = sorted(
            emotion_totals.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        # エンゲージメントスコア（発言の均等性で評価）
        speakers = set(s.get("speaker_id") for s in segments if s.get("speaker_id"))
        if len(speakers) > 1:
            speaker_counts = {}
            for s in segments:
                sid = s.get("speaker_id")
                if sid:
                    speaker_counts[sid] = speaker_counts.get(sid, 0) + 1

            counts = list(speaker_counts.values())
            avg_count = sum(counts) / len(counts)
            variance = sum((c - avg_count) ** 2 for c in counts) / len(counts)
            engagement_score = max(0, 1 - (variance / (avg_count ** 2) if avg_count > 0 else 0))
        else:
            engagement_score = 0.5

        # コラボレーションスコア
        interactions = await self.speaker_analyzer.analyze_interactions(segments)
        collaboration_score = min(len(interactions) / 10, 1.0) if interactions else 0.3

        # テンションレベル（ネガティブ感情と割り込みから）
        negative_ratio = len([s for s in all_sentiments if s < -0.2]) / len(all_sentiments) if all_sentiments else 0
        interruption_count = sum(i.interruption_count for i in interactions)
        tension_level = min((negative_ratio + interruption_count / 20) / 2, 1.0)

        # エネルギーレベル（発言頻度と感情の強さから）
        emotion_intensity = sum(score for _, score in all_emotions) / len(all_emotions) if all_emotions else 0.5
        energy_level = emotion_intensity

        return MeetingAtmosphere(
            overall_sentiment=overall_sentiment,
            engagement_score=engagement_score,
            collaboration_score=collaboration_score,
            tension_level=tension_level,
            energy_level=energy_level,
            dominant_emotions=dominant_emotions,
            highlights=highlights[:5],
            concerns=concerns[:5],
        )


# グローバルインスタンス
emotion_analyzer = EmotionAnalyzer()
tone_analyzer = ToneAnalyzer()
speaker_analyzer = SpeakerAnalyzer()
meeting_analyzer = MeetingAnalyzer()
