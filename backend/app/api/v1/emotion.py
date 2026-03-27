"""話者分析・感情分析APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.emotion_analysis_service import (
    emotion_analyzer,
    tone_analyzer,
    speaker_analyzer,
    meeting_analyzer,
    Emotion,
    Sentiment,
)

router = APIRouter(prefix="/emotion", tags=["emotion"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === 感情分析 ===

class AnalyzeSegmentRequest(BaseModel):
    text: str
    audio_features: Optional[dict] = None


@router.post("/analyze/segment")
async def analyze_segment(
    request: AnalyzeSegmentRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セグメントの感情を分析"""
    result = await emotion_analyzer.analyze_segment(
        text=request.text,
        audio_features=request.audio_features,
    )

    return {
        "emotions": [
            {
                "emotion": e.emotion.value,
                "score": e.score,
                "confidence": e.confidence,
            }
            for e in result["emotions"]
        ],
        "sentiment": {
            "sentiment": result["sentiment"].sentiment.value,
            "score": result["sentiment"].score,
            "confidence": result["sentiment"].confidence,
        },
        "primary_emotion": {
            "emotion": result["primary_emotion"].emotion.value,
            "score": result["primary_emotion"].score,
        } if result["primary_emotion"] else None,
    }


class AnalyzeBatchRequest(BaseModel):
    segments: List[dict]


@router.post("/analyze/batch")
async def analyze_batch(
    request: AnalyzeBatchRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """複数セグメントをバッチ分析"""
    results = []
    for segment in request.segments:
        result = await emotion_analyzer.analyze_segment(
            text=segment.get("text", ""),
            audio_features=segment.get("audio_features"),
        )
        results.append({
            "segment_id": segment.get("id"),
            "primary_emotion": result["primary_emotion"].emotion.value if result["primary_emotion"] else None,
            "sentiment_score": result["sentiment"].score,
        })

    return {"results": results, "count": len(results)}


# === トーン分析 ===

class AnalyzeToneRequest(BaseModel):
    text: str
    audio_features: Optional[dict] = None


@router.post("/analyze/tone")
async def analyze_tone(
    request: AnalyzeToneRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """トーンを分析"""
    result = await tone_analyzer.analyze_tone(
        text=request.text,
        audio_features=request.audio_features,
    )

    return {
        "primary_tone": result.primary_tone.value,
        "tones": {k.value: v for k, v in result.tones.items()},
        "speech_characteristics": {
            "speech_rate": result.speech_rate,
            "pitch_variation": result.pitch_variation,
            "volume_level": result.volume_level,
            "pause_frequency": result.pause_frequency,
        },
    }


# === 話者分析 ===

class AnalyzeSpeakerRequest(BaseModel):
    speaker_id: str
    segments: List[dict]


@router.post("/analyze/speaker")
async def analyze_speaker(
    request: AnalyzeSpeakerRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """話者を分析"""
    profile = await speaker_analyzer.analyze_speaker(
        speaker_id=request.speaker_id,
        segments=request.segments,
    )

    return {
        "speaker_id": profile.speaker_id,
        "name": profile.name,
        "statistics": {
            "total_speaking_time_ms": profile.total_speaking_time_ms,
            "segment_count": profile.segment_count,
            "average_segment_length_ms": profile.average_segment_length_ms,
            "word_count": profile.word_count,
            "average_words_per_segment": profile.average_words_per_segment,
        },
        "dominant_emotion": profile.dominant_emotion.value if profile.dominant_emotion else None,
        "average_sentiment": profile.average_sentiment,
    }


class AnalyzeInteractionsRequest(BaseModel):
    segments: List[dict]


@router.post("/analyze/interactions")
async def analyze_interactions(
    request: AnalyzeInteractionsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """対話パターンを分析"""
    patterns = await speaker_analyzer.analyze_interactions(request.segments)

    return {
        "interactions": [
            {
                "speaker_a": p.speaker_a,
                "speaker_b": p.speaker_b,
                "interaction_count": p.interaction_count,
                "average_response_time_ms": p.average_response_time_ms,
                "overlap_count": p.overlap_count,
                "interruption_count": p.interruption_count,
            }
            for p in patterns
        ],
        "total_interactions": sum(p.interaction_count for p in patterns),
    }


# === 会議分析 ===

class AnalyzeMeetingRequest(BaseModel):
    segments: List[dict]
    metadata: Optional[dict] = None


@router.post("/analyze/meeting")
async def analyze_meeting(
    request: AnalyzeMeetingRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """会議全体を分析"""
    atmosphere = await meeting_analyzer.analyze_meeting(
        segments=request.segments,
        metadata=request.metadata,
    )

    return {
        "scores": {
            "overall_sentiment": atmosphere.overall_sentiment,
            "engagement": atmosphere.engagement_score,
            "collaboration": atmosphere.collaboration_score,
            "tension": atmosphere.tension_level,
            "energy": atmosphere.energy_level,
        },
        "dominant_emotions": [
            {"emotion": e.value, "score": s}
            for e, s in atmosphere.dominant_emotions
        ],
        "highlights": atmosphere.highlights,
        "concerns": atmosphere.concerns,
        "summary": _generate_meeting_summary(atmosphere),
    }


def _generate_meeting_summary(atmosphere) -> str:
    """会議サマリーを生成"""
    sentiment_desc = "ポジティブ" if atmosphere.overall_sentiment > 0.2 else (
        "ネガティブ" if atmosphere.overall_sentiment < -0.2 else "中立的"
    )

    engagement_desc = "高い" if atmosphere.engagement_score > 0.7 else (
        "低い" if atmosphere.engagement_score < 0.3 else "標準的"
    )

    return (
        f"全体的に{sentiment_desc}な雰囲気で、参加者のエンゲージメントは{engagement_desc}でした。"
        f"コラボレーションスコアは{atmosphere.collaboration_score:.0%}、"
        f"エネルギーレベルは{atmosphere.energy_level:.0%}です。"
    )


# === 文字起こし連携 ===

@router.post("/transcriptions/{transcription_id}/analyze")
async def analyze_transcription(
    transcription_id: str,
    include_emotions: bool = Query(True),
    include_tones: bool = Query(True),
    include_interactions: bool = Query(True),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """文字起こしを分析"""
    # 実際の実装ではDBから文字起こしを取得
    # ここではサンプルデータを使用
    sample_segments = [
        {
            "id": "seg_1",
            "text": "本日はお集まりいただきありがとうございます。",
            "speaker_id": "speaker_1",
            "start_time_ms": 0,
            "end_time_ms": 3000,
        },
        {
            "id": "seg_2",
            "text": "新製品の進捗について報告させていただきます。",
            "speaker_id": "speaker_1",
            "start_time_ms": 3000,
            "end_time_ms": 6000,
        },
        {
            "id": "seg_3",
            "text": "素晴らしい進捗ですね。質問があります。",
            "speaker_id": "speaker_2",
            "start_time_ms": 6000,
            "end_time_ms": 9000,
        },
    ]

    result = {
        "transcription_id": transcription_id,
        "analyzed_at": datetime.utcnow().isoformat(),
    }

    if include_emotions:
        emotions_data = []
        for seg in sample_segments:
            analysis = await emotion_analyzer.analyze_segment(seg["text"])
            emotions_data.append({
                "segment_id": seg["id"],
                "primary_emotion": analysis["primary_emotion"].emotion.value if analysis["primary_emotion"] else None,
                "sentiment": analysis["sentiment"].score,
            })
        result["emotions"] = emotions_data

    if include_tones:
        tones_data = []
        for seg in sample_segments:
            tone = await tone_analyzer.analyze_tone(seg["text"])
            tones_data.append({
                "segment_id": seg["id"],
                "primary_tone": tone.primary_tone.value,
            })
        result["tones"] = tones_data

    if include_interactions:
        patterns = await speaker_analyzer.analyze_interactions(sample_segments)
        result["interactions"] = [
            {
                "speakers": [p.speaker_a, p.speaker_b],
                "count": p.interaction_count,
            }
            for p in patterns
        ]

    # 会議雰囲気
    atmosphere = await meeting_analyzer.analyze_meeting(sample_segments)
    result["meeting_atmosphere"] = {
        "overall_sentiment": atmosphere.overall_sentiment,
        "engagement": atmosphere.engagement_score,
        "energy": atmosphere.energy_level,
    }

    return result


# === 感情タイムライン ===

@router.get("/transcriptions/{transcription_id}/timeline")
async def get_emotion_timeline(
    transcription_id: str,
    resolution: str = Query("segment", enum=["segment", "minute", "5min"]),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """感情タイムラインを取得"""
    # サンプルタイムラインデータ
    timeline = [
        {"time_ms": 0, "sentiment": 0.5, "emotion": "neutral"},
        {"time_ms": 30000, "sentiment": 0.7, "emotion": "happy"},
        {"time_ms": 60000, "sentiment": 0.3, "emotion": "neutral"},
        {"time_ms": 90000, "sentiment": -0.2, "emotion": "sad"},
        {"time_ms": 120000, "sentiment": 0.6, "emotion": "happy"},
    ]

    return {
        "transcription_id": transcription_id,
        "resolution": resolution,
        "timeline": timeline,
        "summary": {
            "avg_sentiment": sum(t["sentiment"] for t in timeline) / len(timeline),
            "sentiment_range": {
                "min": min(t["sentiment"] for t in timeline),
                "max": max(t["sentiment"] for t in timeline),
            },
        },
    }


# === 比較分析 ===

@router.post("/compare")
async def compare_meetings(
    transcription_ids: List[str],
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """複数会議を比較"""
    # サンプル比較データ
    comparisons = []
    for tid in transcription_ids:
        comparisons.append({
            "transcription_id": tid,
            "overall_sentiment": 0.4 + (hash(tid) % 10) / 20,
            "engagement": 0.5 + (hash(tid) % 10) / 25,
            "collaboration": 0.6 + (hash(tid) % 10) / 30,
            "duration_minutes": 30 + (hash(tid) % 60),
        })

    return {
        "comparisons": comparisons,
        "insights": [
            "会議Aは最も高いエンゲージメントを示しています",
            "全体的にポジティブな傾向が見られます",
        ],
    }
