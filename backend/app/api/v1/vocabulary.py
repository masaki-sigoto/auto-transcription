import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import csv
import io

from app.core.database import get_db
from app.services.vocabulary_service import VocabularyService, AutoCorrectionService

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================

class CreateDictionaryRequest(BaseModel):
    name: str
    description: Optional[str] = None
    language: str = "ja"
    team_id: Optional[uuid.UUID] = None
    is_shared: bool = False


class UpdateDictionaryRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_shared: Optional[bool] = None


class DictionaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    language: str
    is_active: bool
    is_shared: bool
    word_count: int
    usage_count: int
    created_at: str


class AddWordRequest(BaseModel):
    word: str
    reading: Optional[str] = None
    pronunciation: Optional[str] = None
    aliases: list[str] = []
    category: Optional[str] = None
    tags: list[str] = []
    priority: int = 0
    boost_factor: float = 1.0
    notes: Optional[str] = None


class UpdateWordRequest(BaseModel):
    word: Optional[str] = None
    reading: Optional[str] = None
    pronunciation: Optional[str] = None
    aliases: Optional[list[str]] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    priority: Optional[int] = None
    boost_factor: Optional[float] = None
    notes: Optional[str] = None


class WordResponse(BaseModel):
    id: uuid.UUID
    word: str
    reading: Optional[str]
    pronunciation: Optional[str]
    aliases: list[str]
    category: Optional[str]
    tags: list[str]
    priority: int
    boost_factor: float
    notes: Optional[str]
    created_at: str


class CreateRuleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: str  # replace, regex
    pattern: str
    replacement: str
    case_sensitive: bool = False
    team_id: Optional[uuid.UUID] = None
    is_shared: bool = False


class RuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    rule_type: str
    pattern: str
    replacement: str
    case_sensitive: bool
    is_active: bool
    is_shared: bool
    usage_count: int
    created_at: str


class ApplyVocabularyRequest(BaseModel):
    text: str
    dictionary_ids: list[uuid.UUID] = []
    apply_rules: bool = True


class ApplyVocabularyResponse(BaseModel):
    corrected_text: str
    corrections: list[dict]


# =============================================================================
# 辞書管理
# =============================================================================

@router.post("/dictionaries", response_model=DictionaryResponse, status_code=201)
async def create_dictionary(
    request: CreateDictionaryRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """辞書を作成"""
    service = VocabularyService(db)
    dictionary = await service.create_dictionary(
        user_id=user_id,
        name=request.name,
        description=request.description,
        language=request.language,
        team_id=request.team_id,
        is_shared=request.is_shared,
    )

    return DictionaryResponse(
        id=dictionary.id,
        name=dictionary.name,
        description=dictionary.description,
        language=dictionary.language,
        is_active=dictionary.is_active,
        is_shared=dictionary.is_shared,
        word_count=dictionary.word_count or 0,
        usage_count=dictionary.usage_count or 0,
        created_at=dictionary.created_at.isoformat(),
    )


@router.get("/dictionaries", response_model=list[DictionaryResponse])
async def list_dictionaries(
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """辞書一覧を取得"""
    service = VocabularyService(db)
    dictionaries = await service.list_dictionaries(user_id, team_id)

    return [
        DictionaryResponse(
            id=d.id,
            name=d.name,
            description=d.description,
            language=d.language,
            is_active=d.is_active,
            is_shared=d.is_shared,
            word_count=d.word_count or 0,
            usage_count=d.usage_count or 0,
            created_at=d.created_at.isoformat(),
        )
        for d in dictionaries
    ]


@router.get("/dictionaries/{dictionary_id}", response_model=DictionaryResponse)
async def get_dictionary(
    dictionary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """辞書を取得"""
    service = VocabularyService(db)
    dictionary = await service.get_dictionary(dictionary_id)

    if not dictionary:
        raise HTTPException(status_code=404, detail="Dictionary not found")

    return DictionaryResponse(
        id=dictionary.id,
        name=dictionary.name,
        description=dictionary.description,
        language=dictionary.language,
        is_active=dictionary.is_active,
        is_shared=dictionary.is_shared,
        word_count=dictionary.word_count or 0,
        usage_count=dictionary.usage_count or 0,
        created_at=dictionary.created_at.isoformat(),
    )


@router.patch("/dictionaries/{dictionary_id}", response_model=DictionaryResponse)
async def update_dictionary(
    dictionary_id: uuid.UUID,
    request: UpdateDictionaryRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """辞書を更新"""
    service = VocabularyService(db)
    dictionary = await service.update_dictionary(
        dictionary_id=dictionary_id,
        name=request.name,
        description=request.description,
        is_active=request.is_active,
        is_shared=request.is_shared,
    )

    if not dictionary:
        raise HTTPException(status_code=404, detail="Dictionary not found")

    return DictionaryResponse(
        id=dictionary.id,
        name=dictionary.name,
        description=dictionary.description,
        language=dictionary.language,
        is_active=dictionary.is_active,
        is_shared=dictionary.is_shared,
        word_count=dictionary.word_count or 0,
        usage_count=dictionary.usage_count or 0,
        created_at=dictionary.created_at.isoformat(),
    )


@router.delete("/dictionaries/{dictionary_id}", status_code=204)
async def delete_dictionary(
    dictionary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """辞書を削除"""
    service = VocabularyService(db)
    if not await service.delete_dictionary(dictionary_id):
        raise HTTPException(status_code=404, detail="Dictionary not found")


# =============================================================================
# ワード管理
# =============================================================================

@router.post("/dictionaries/{dictionary_id}/words", response_model=WordResponse, status_code=201)
async def add_word(
    dictionary_id: uuid.UUID,
    request: AddWordRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワードを追加"""
    service = VocabularyService(db)
    word = await service.add_word(
        dictionary_id=dictionary_id,
        word=request.word,
        reading=request.reading,
        pronunciation=request.pronunciation,
        aliases=request.aliases,
        category=request.category,
        tags=request.tags,
        priority=request.priority,
        boost_factor=request.boost_factor,
        notes=request.notes,
    )

    return WordResponse(
        id=word.id,
        word=word.word,
        reading=word.reading,
        pronunciation=word.pronunciation,
        aliases=word.aliases or [],
        category=word.category,
        tags=word.tags or [],
        priority=word.priority,
        boost_factor=float(word.boost_factor),
        notes=word.notes,
        created_at=word.created_at.isoformat(),
    )


@router.post("/dictionaries/{dictionary_id}/words/import")
async def import_words(
    dictionary_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """CSVファイルからワードをインポート"""
    service = VocabularyService(db)

    # CSVを解析
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    words = []
    for row in reader:
        words.append({
            "word": row.get("word", "").strip(),
            "reading": row.get("reading", "").strip() or None,
            "pronunciation": row.get("pronunciation", "").strip() or None,
            "aliases": [a.strip() for a in row.get("aliases", "").split(",") if a.strip()],
            "category": row.get("category", "").strip() or None,
            "tags": [t.strip() for t in row.get("tags", "").split(",") if t.strip()],
            "priority": int(row.get("priority", 0) or 0),
            "boost_factor": float(row.get("boost_factor", 1.0) or 1.0),
            "notes": row.get("notes", "").strip() or None,
        })

    # 空のワードを除外
    words = [w for w in words if w["word"]]

    count = await service.add_words_bulk(dictionary_id, words)

    return {"imported": count}


@router.get("/dictionaries/{dictionary_id}/words", response_model=list[WordResponse])
async def list_words(
    dictionary_id: uuid.UUID,
    query: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワード一覧を取得"""
    service = VocabularyService(db)

    if query:
        words = await service.search_words(dictionary_id, query, category)
    else:
        dictionary = await service.get_dictionary(dictionary_id)
        if not dictionary:
            raise HTTPException(status_code=404, detail="Dictionary not found")
        words = dictionary.words

    return [
        WordResponse(
            id=w.id,
            word=w.word,
            reading=w.reading,
            pronunciation=w.pronunciation,
            aliases=w.aliases or [],
            category=w.category,
            tags=w.tags or [],
            priority=w.priority,
            boost_factor=float(w.boost_factor),
            notes=w.notes,
            created_at=w.created_at.isoformat(),
        )
        for w in words
    ]


@router.patch("/words/{word_id}", response_model=WordResponse)
async def update_word(
    word_id: uuid.UUID,
    request: UpdateWordRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワードを更新"""
    service = VocabularyService(db)
    word = await service.update_word(
        word_id=word_id,
        word=request.word,
        reading=request.reading,
        pronunciation=request.pronunciation,
        aliases=request.aliases,
        category=request.category,
        tags=request.tags,
        priority=request.priority,
        boost_factor=request.boost_factor,
        notes=request.notes,
    )

    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    return WordResponse(
        id=word.id,
        word=word.word,
        reading=word.reading,
        pronunciation=word.pronunciation,
        aliases=word.aliases or [],
        category=word.category,
        tags=word.tags or [],
        priority=word.priority,
        boost_factor=float(word.boost_factor),
        notes=word.notes,
        created_at=word.created_at.isoformat(),
    )


@router.delete("/words/{word_id}", status_code=204)
async def delete_word(
    word_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ワードを削除"""
    service = VocabularyService(db)
    if not await service.delete_word(word_id):
        raise HTTPException(status_code=404, detail="Word not found")


# =============================================================================
# 自動修正ルール
# =============================================================================

@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    request: CreateRuleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """自動修正ルールを作成"""
    service = AutoCorrectionService(db)
    rule = await service.create_rule(
        user_id=user_id,
        name=request.name,
        description=request.description,
        rule_type=request.rule_type,
        pattern=request.pattern,
        replacement=request.replacement,
        case_sensitive=request.case_sensitive,
        team_id=request.team_id,
        is_shared=request.is_shared,
    )

    return RuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        replacement=rule.replacement,
        case_sensitive=rule.case_sensitive,
        is_active=rule.is_active,
        is_shared=rule.is_shared,
        usage_count=rule.usage_count or 0,
        created_at=rule.created_at.isoformat(),
    )


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """自動修正ルール一覧を取得"""
    service = AutoCorrectionService(db)
    rules = await service.list_rules(user_id, team_id)

    return [
        RuleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            rule_type=r.rule_type,
            pattern=r.pattern,
            replacement=r.replacement,
            case_sensitive=r.case_sensitive,
            is_active=r.is_active,
            is_shared=r.is_shared,
            usage_count=r.usage_count or 0,
            created_at=r.created_at.isoformat(),
        )
        for r in rules
    ]


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """自動修正ルールを削除"""
    service = AutoCorrectionService(db)
    if not await service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")


# =============================================================================
# テキスト処理
# =============================================================================

@router.post("/apply", response_model=ApplyVocabularyResponse)
async def apply_vocabulary(
    request: ApplyVocabularyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """語彙・ルールをテキストに適用"""
    vocab_service = VocabularyService(db)
    rule_service = AutoCorrectionService(db)

    all_corrections = []
    corrected_text = request.text

    # 辞書を適用
    if request.dictionary_ids:
        dictionaries = []
        for dict_id in request.dictionary_ids:
            dictionary = await vocab_service.get_dictionary(dict_id)
            if dictionary:
                dictionaries.append(dictionary)

        if dictionaries:
            vocab_map = vocab_service.build_vocabulary_map(dictionaries)
            corrected_text, vocab_corrections = vocab_service.apply_vocabulary(
                corrected_text, vocab_map
            )
            all_corrections.extend(vocab_corrections)

    # 修正ルールを適用
    if request.apply_rules:
        rules = await rule_service.list_rules(user_id)
        corrected_text, rule_corrections = rule_service.apply_rules(
            corrected_text, rules
        )
        all_corrections.extend(rule_corrections)

    return ApplyVocabularyResponse(
        corrected_text=corrected_text,
        corrections=all_corrections,
    )
