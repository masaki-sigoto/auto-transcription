"""翻訳APIエンドポイント"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import get_settings
from app.services.translation_service import (
    TranslationService,
    SupportedLanguage,
    LANGUAGE_NAMES,
)
from app.services.multilingual_service import MultilingualService, LanguageDetectionService

router = APIRouter(prefix="/translation", tags=["translation"])


class TranslateTextRequest(BaseModel):
    """テキスト翻訳リクエスト"""

    text: str
    target_language: SupportedLanguage
    source_language: SupportedLanguage | None = None


class TranslateTextResponse(BaseModel):
    """テキスト翻訳レスポンス"""

    original_text: str
    translated_text: str
    source_language: str
    target_language: str


class TranslateTranscriptionRequest(BaseModel):
    """文字起こし翻訳リクエスト"""

    target_languages: list[SupportedLanguage]


class LanguageInfo(BaseModel):
    """言語情報"""

    code: str
    name: str


def get_translation_service() -> TranslationService:
    """翻訳サービスを取得"""
    return TranslationService(settings.OPENAI_API_KEY)


@router.get("/languages", response_model=list[LanguageInfo])
async def list_supported_languages():
    """サポートする言語一覧を取得"""
    return [
        LanguageInfo(code=lang.value, name=LANGUAGE_NAMES[lang])
        for lang in SupportedLanguage
    ]


@router.post("/text", response_model=TranslateTextResponse)
async def translate_text(
    request: TranslateTextRequest,
    service: TranslationService = Depends(get_translation_service),
):
    """テキストを翻訳"""
    try:
        result = await service.translate(
            request.text,
            request.target_language,
            request.source_language,
        )
        return TranslateTextResponse(
            original_text=result.original_text,
            translated_text=result.translated_text,
            source_language=result.source_language,
            target_language=result.target_language,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@router.post("/detect")
async def detect_language(
    text: str,
    service: TranslationService = Depends(get_translation_service),
):
    """テキストの言語を検出"""
    language = await service.detect_language(text)
    return {
        "language": language.value,
        "name": LANGUAGE_NAMES[language],
    }


@router.post("/transcriptions/{transcription_id}/translate")
async def translate_transcription(
    transcription_id: UUID,
    request: TranslateTranscriptionRequest,
    db: AsyncSession = Depends(get_db),
    translation_service: TranslationService = Depends(get_translation_service),
):
    """文字起こしを複数言語に翻訳"""
    service = MultilingualService(db, translation_service)

    try:
        result = await service.translate_transcription(
            transcription_id,
            request.target_languages,
        )
        return {
            "transcription_id": str(result.transcription_id),
            "original_language": result.original_language,
            "translations": result.translations,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@router.get(
    "/transcriptions/{transcription_id}/subtitle",
    response_class=PlainTextResponse,
)
async def get_translated_subtitle(
    transcription_id: UUID,
    target_language: SupportedLanguage = Query(...),
    format: str = Query("srt", regex="^(srt|vtt)$"),
    db: AsyncSession = Depends(get_db),
    translation_service: TranslationService = Depends(get_translation_service),
):
    """翻訳された字幕を取得"""
    service = MultilingualService(db, translation_service)

    try:
        subtitle = await service.get_subtitle_in_language(
            transcription_id,
            target_language,
            format,
        )

        content_type = "text/plain"
        if format == "vtt":
            content_type = "text/vtt"

        return PlainTextResponse(
            content=subtitle,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="subtitle_{target_language.value}.{format}"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/suggest")
async def suggest_translation_languages(
    source_language: SupportedLanguage,
    translation_service: TranslationService = Depends(get_translation_service),
):
    """おすすめの翻訳言語を提案"""
    detection_service = LanguageDetectionService(translation_service)
    suggestions = await detection_service.suggest_languages(source_language)

    return {
        "source_language": {
            "code": source_language.value,
            "name": LANGUAGE_NAMES[source_language],
        },
        "suggested_languages": [
            {"code": lang.value, "name": LANGUAGE_NAMES[lang]} for lang in suggestions
        ],
    }


# === 拡張機能: 用語集・翻訳メモリ・同時通訳 ===

from typing import Optional, List
from app.services.translation_service import (
    glossary_manager,
    translation_memory,
    SimultaneousInterpreter,
    SubtitleGenerator,
)


class CreateGlossaryRequest(BaseModel):
    name: str


@router.post("/glossaries")
async def create_glossary(request: CreateGlossaryRequest):
    """用語集を作成"""
    glossary_id = await glossary_manager.create_glossary(request.name, "default-tenant")
    return {"glossary_id": glossary_id, "name": request.name}


class AddGlossaryEntryRequest(BaseModel):
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    context: Optional[str] = None


@router.post("/glossaries/{glossary_id}/entries")
async def add_glossary_entry(glossary_id: str, request: AddGlossaryEntryRequest):
    """用語集エントリを追加"""
    entry = await glossary_manager.add_entry(
        glossary_id=glossary_id,
        source_term=request.source_term,
        target_term=request.target_term,
        source_language=request.source_language,
        target_language=request.target_language,
        context=request.context,
    )
    return {"id": entry.id, "source_term": entry.source_term, "target_term": entry.target_term}


@router.get("/glossaries/{glossary_id}/entries")
async def get_glossary_entries(
    glossary_id: str,
    source_language: Optional[str] = None,
    target_language: Optional[str] = None,
):
    """用語集エントリを取得"""
    entries = await glossary_manager.get_entries(glossary_id, source_language, target_language)
    return {
        "entries": [
            {
                "id": e.id,
                "source_term": e.source_term,
                "target_term": e.target_term,
                "source_language": e.source_language,
                "target_language": e.target_language,
            }
            for e in entries
        ],
        "count": len(entries),
    }


class ImportGlossaryRequest(BaseModel):
    entries: List[dict]


@router.post("/glossaries/{glossary_id}/import")
async def import_glossary(glossary_id: str, request: ImportGlossaryRequest):
    """用語集をインポート"""
    count = await glossary_manager.import_glossary(glossary_id, request.entries)
    return {"imported": count}


@router.delete("/glossaries/{glossary_id}")
async def delete_glossary(glossary_id: str):
    """用語集を削除"""
    success = await glossary_manager.delete_glossary(glossary_id)
    if not success:
        raise HTTPException(status_code=404, detail="Glossary not found")
    return {"status": "deleted"}


# === 翻訳メモリ ===

class SearchMemoryRequest(BaseModel):
    text: str
    source_language: str
    target_language: str
    min_similarity: float = 0.8


@router.post("/memory/search")
async def search_translation_memory(request: SearchMemoryRequest):
    """翻訳メモリを検索"""
    results = await translation_memory.search(
        tenant_id="default-tenant",
        text=request.text,
        source_language=request.source_language,
        target_language=request.target_language,
        min_similarity=request.min_similarity,
    )
    return {
        "matches": [
            {
                "id": r.id,
                "source_text": r.source_text,
                "translated_text": r.translated_text,
                "similarity_score": r.similarity_score,
            }
            for r in results
        ],
        "count": len(results),
    }


@router.get("/memory/statistics")
async def get_memory_statistics():
    """翻訳メモリ統計"""
    stats = await translation_memory.get_statistics("default-tenant")
    return stats


# === 同時通訳 ===

class CreateInterpreterSessionRequest(BaseModel):
    source_language: SupportedLanguage
    target_languages: List[SupportedLanguage]


@router.post("/interpreter/sessions")
async def create_interpreter_session(
    request: CreateInterpreterSessionRequest,
    service: TranslationService = Depends(get_translation_service),
):
    """同時通訳セッションを作成"""
    interpreter = SimultaneousInterpreter(service)
    session_id = await interpreter.create_session(
        source_language=request.source_language,
        target_languages=request.target_languages,
    )
    return {
        "session_id": session_id,
        "source_language": request.source_language.value,
        "target_languages": [l.value for l in request.target_languages],
    }


# === 字幕生成 ===

class GenerateSubtitlesRequest(BaseModel):
    segments: List[dict]
    source_language: SupportedLanguage
    target_languages: List[SupportedLanguage]
    format: str = "vtt"


@router.post("/subtitles/generate")
async def generate_subtitles(
    request: GenerateSubtitlesRequest,
    service: TranslationService = Depends(get_translation_service),
):
    """多言語字幕を生成"""
    generator = SubtitleGenerator(service)
    try:
        subtitles = await generator.generate_subtitles(
            segments=request.segments,
            target_languages=request.target_languages,
            source_language=request.source_language,
            format=request.format,
        )
        return {
            "subtitles": subtitles,
            "format": request.format,
            "languages": [l.value for l in request.target_languages],
        }
    finally:
        await service.close()
