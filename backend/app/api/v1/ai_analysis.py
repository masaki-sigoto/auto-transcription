"""AI分析APIエンドポイント"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.services.ai_analysis_service import AIAnalysisService

router = APIRouter(prefix="/ai", tags=["ai-analysis"])


class QuestionRequest(BaseModel):
    """質問リクエスト"""
    question: str


class SummaryRequest(BaseModel):
    """要約リクエスト"""
    style: str = "concise"  # concise, detailed, bullet_points


@router.post("/transcriptions/{transcription_id}/minutes")
async def generate_meeting_minutes(
    transcription_id: UUID,
    include_action_items: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """議事録を自動生成"""
    service = AIAnalysisService(db)

    try:
        minutes = await service.generate_meeting_minutes(
            transcription_id,
            include_action_items,
        )

        return {
            "title": minutes.title,
            "date": minutes.date,
            "participants": minutes.participants,
            "summary": minutes.summary,
            "key_points": minutes.key_points,
            "action_items": minutes.action_items,
            "decisions": minutes.decisions,
            "next_steps": minutes.next_steps,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate minutes: {str(e)}")
    finally:
        await service.close()


@router.post("/transcriptions/{transcription_id}/sentiment")
async def analyze_sentiment(
    transcription_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """感情分析を実行"""
    service = AIAnalysisService(db)

    try:
        result = await service.analyze_sentiment(transcription_id)

        return {
            "overall_sentiment": result.overall_sentiment,
            "sentiment_score": result.sentiment_score,
            "segments": result.segments,
            "speaker_sentiments": result.speaker_sentiments,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {str(e)}")
    finally:
        await service.close()


@router.post("/transcriptions/{transcription_id}/keywords")
async def extract_keywords(
    transcription_id: UUID,
    max_keywords: int = Query(20, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
):
    """キーワードを抽出"""
    service = AIAnalysisService(db)

    try:
        result = await service.extract_keywords(transcription_id, max_keywords)

        return {
            "keywords": result.keywords,
            "topics": result.topics,
            "entities": result.entities,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Keyword extraction failed: {str(e)}")
    finally:
        await service.close()


@router.post("/transcriptions/{transcription_id}/question")
async def answer_question(
    transcription_id: UUID,
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
):
    """質問に回答"""
    service = AIAnalysisService(db)

    try:
        result = await service.answer_question(transcription_id, request.question)

        return {
            "question": result.question,
            "answer": result.answer,
            "confidence": result.confidence,
            "relevant_segments": result.relevant_segments,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {str(e)}")
    finally:
        await service.close()


@router.post("/transcriptions/{transcription_id}/summary")
async def generate_summary(
    transcription_id: UUID,
    request: SummaryRequest,
    db: AsyncSession = Depends(get_db),
):
    """要約を生成"""
    service = AIAnalysisService(db)

    try:
        summary = await service.generate_summary(transcription_id, request.style)

        return {
            "summary": summary,
            "style": request.style,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")
    finally:
        await service.close()


@router.post("/transcriptions/{transcription_id}/analyze-all")
async def analyze_all(
    transcription_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """すべての分析を実行"""
    service = AIAnalysisService(db)

    try:
        # 並列実行
        import asyncio

        minutes_task = service.generate_meeting_minutes(transcription_id)
        sentiment_task = service.analyze_sentiment(transcription_id)
        keywords_task = service.extract_keywords(transcription_id)
        summary_task = service.generate_summary(transcription_id, "concise")

        minutes, sentiment, keywords, summary = await asyncio.gather(
            minutes_task,
            sentiment_task,
            keywords_task,
            summary_task,
            return_exceptions=True,
        )

        result = {}

        if not isinstance(minutes, Exception):
            result["minutes"] = {
                "title": minutes.title,
                "summary": minutes.summary,
                "key_points": minutes.key_points,
                "action_items": minutes.action_items,
            }

        if not isinstance(sentiment, Exception):
            result["sentiment"] = {
                "overall_sentiment": sentiment.overall_sentiment,
                "sentiment_score": sentiment.sentiment_score,
            }

        if not isinstance(keywords, Exception):
            result["keywords"] = {
                "top_keywords": keywords.keywords[:10],
                "topics": keywords.topics,
            }

        if not isinstance(summary, Exception):
            result["summary"] = summary

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
    finally:
        await service.close()
