import uuid
import re
from typing import Optional
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from difflib import SequenceMatcher

from app.models.vocabulary import (
    VocabularyDictionary,
    VocabularyWord,
    TranscriptionVocabulary,
    AutoCorrectionRule,
)


class VocabularyService:
    """語彙辞書サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # 辞書管理
    # =========================================================================

    async def create_dictionary(
        self,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        language: str = "ja",
        team_id: Optional[uuid.UUID] = None,
        is_shared: bool = False,
    ) -> VocabularyDictionary:
        """辞書を作成"""
        dictionary = VocabularyDictionary(
            user_id=user_id,
            team_id=team_id,
            name=name,
            description=description,
            language=language,
            is_shared=is_shared,
        )
        self.db.add(dictionary)
        await self.db.commit()
        return dictionary

    async def get_dictionary(
        self,
        dictionary_id: uuid.UUID,
    ) -> Optional[VocabularyDictionary]:
        """辞書を取得"""
        query = (
            select(VocabularyDictionary)
            .where(VocabularyDictionary.id == dictionary_id)
            .options(selectinload(VocabularyDictionary.words))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_dictionaries(
        self,
        user_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
        include_shared: bool = True,
    ) -> list[VocabularyDictionary]:
        """辞書一覧を取得"""
        conditions = [VocabularyDictionary.user_id == user_id]

        if team_id and include_shared:
            # チーム共有辞書も含める
            conditions = [
                or_(
                    VocabularyDictionary.user_id == user_id,
                    and_(
                        VocabularyDictionary.team_id == team_id,
                        VocabularyDictionary.is_shared == True,
                    ),
                )
            ]

        query = (
            select(VocabularyDictionary)
            .where(*conditions)
            .order_by(VocabularyDictionary.created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_dictionary(
        self,
        dictionary_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_shared: Optional[bool] = None,
    ) -> Optional[VocabularyDictionary]:
        """辞書を更新"""
        dictionary = await self.get_dictionary(dictionary_id)
        if not dictionary:
            return None

        if name:
            dictionary.name = name
        if description is not None:
            dictionary.description = description
        if is_active is not None:
            dictionary.is_active = is_active
        if is_shared is not None:
            dictionary.is_shared = is_shared

        await self.db.commit()
        return dictionary

    async def delete_dictionary(self, dictionary_id: uuid.UUID) -> bool:
        """辞書を削除"""
        dictionary = await self.get_dictionary(dictionary_id)
        if not dictionary:
            return False

        await self.db.delete(dictionary)
        await self.db.commit()
        return True

    # =========================================================================
    # ワード管理
    # =========================================================================

    async def add_word(
        self,
        dictionary_id: uuid.UUID,
        word: str,
        reading: Optional[str] = None,
        pronunciation: Optional[str] = None,
        aliases: list[str] = None,
        category: Optional[str] = None,
        tags: list[str] = None,
        priority: int = 0,
        boost_factor: float = 1.0,
        notes: Optional[str] = None,
    ) -> VocabularyWord:
        """ワードを追加"""
        vocab_word = VocabularyWord(
            dictionary_id=dictionary_id,
            word=word,
            reading=reading,
            pronunciation=pronunciation,
            aliases=aliases or [],
            category=category,
            tags=tags or [],
            priority=priority,
            boost_factor=str(boost_factor),
            notes=notes,
        )
        self.db.add(vocab_word)

        # 辞書のワード数を更新
        dictionary = await self.get_dictionary(dictionary_id)
        if dictionary:
            dictionary.word_count = (dictionary.word_count or 0) + 1

        await self.db.commit()
        return vocab_word

    async def add_words_bulk(
        self,
        dictionary_id: uuid.UUID,
        words: list[dict],
    ) -> int:
        """ワードを一括追加"""
        count = 0
        for word_data in words:
            vocab_word = VocabularyWord(
                dictionary_id=dictionary_id,
                word=word_data.get("word"),
                reading=word_data.get("reading"),
                pronunciation=word_data.get("pronunciation"),
                aliases=word_data.get("aliases", []),
                category=word_data.get("category"),
                tags=word_data.get("tags", []),
                priority=word_data.get("priority", 0),
                boost_factor=str(word_data.get("boost_factor", 1.0)),
                notes=word_data.get("notes"),
            )
            self.db.add(vocab_word)
            count += 1

        # 辞書のワード数を更新
        dictionary = await self.get_dictionary(dictionary_id)
        if dictionary:
            dictionary.word_count = (dictionary.word_count or 0) + count

        await self.db.commit()
        return count

    async def update_word(
        self,
        word_id: uuid.UUID,
        **kwargs,
    ) -> Optional[VocabularyWord]:
        """ワードを更新"""
        query = select(VocabularyWord).where(VocabularyWord.id == word_id)
        result = await self.db.execute(query)
        word = result.scalar_one_or_none()

        if not word:
            return None

        for key, value in kwargs.items():
            if hasattr(word, key) and value is not None:
                if key == "boost_factor":
                    value = str(value)
                setattr(word, key, value)

        await self.db.commit()
        return word

    async def delete_word(self, word_id: uuid.UUID) -> bool:
        """ワードを削除"""
        query = select(VocabularyWord).where(VocabularyWord.id == word_id)
        result = await self.db.execute(query)
        word = result.scalar_one_or_none()

        if not word:
            return False

        dictionary_id = word.dictionary_id
        await self.db.delete(word)

        # 辞書のワード数を更新
        dictionary = await self.get_dictionary(dictionary_id)
        if dictionary:
            dictionary.word_count = max(0, (dictionary.word_count or 0) - 1)

        await self.db.commit()
        return True

    async def search_words(
        self,
        dictionary_id: uuid.UUID,
        query: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[VocabularyWord]:
        """ワードを検索"""
        conditions = [
            VocabularyWord.dictionary_id == dictionary_id,
            or_(
                VocabularyWord.word.ilike(f"%{query}%"),
                VocabularyWord.reading.ilike(f"%{query}%"),
            ),
        ]

        if category:
            conditions.append(VocabularyWord.category == category)

        stmt = (
            select(VocabularyWord)
            .where(and_(*conditions))
            .order_by(VocabularyWord.priority.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # テキスト処理
    # =========================================================================

    async def get_active_dictionaries(
        self,
        user_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
    ) -> list[VocabularyDictionary]:
        """アクティブな辞書を取得"""
        conditions = [
            VocabularyDictionary.is_active == True,
            or_(
                VocabularyDictionary.user_id == user_id,
                and_(
                    VocabularyDictionary.team_id == team_id,
                    VocabularyDictionary.is_shared == True,
                ) if team_id else False,
            ),
        ]

        query = (
            select(VocabularyDictionary)
            .where(and_(*conditions))
            .options(selectinload(VocabularyDictionary.words))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def build_vocabulary_map(
        self,
        dictionaries: list[VocabularyDictionary],
    ) -> dict[str, VocabularyWord]:
        """語彙マップを構築"""
        vocab_map = {}

        for dictionary in dictionaries:
            for word in dictionary.words:
                # メインワードを追加
                vocab_map[word.word.lower()] = word

                # 別名も追加
                for alias in (word.aliases or []):
                    vocab_map[alias.lower()] = word

                # 読みがなも追加
                if word.reading:
                    vocab_map[word.reading.lower()] = word

        return vocab_map

    def apply_vocabulary(
        self,
        text: str,
        vocab_map: dict[str, VocabularyWord],
        fuzzy_threshold: float = 0.8,
    ) -> tuple[str, list[dict]]:
        """語彙を適用してテキストを修正"""
        corrections = []

        # 単語単位で処理
        words = text.split()
        corrected_words = []

        for original_word in words:
            word_lower = original_word.lower()
            matched_vocab = None

            # 完全一致を試行
            if word_lower in vocab_map:
                matched_vocab = vocab_map[word_lower]
            else:
                # ファジーマッチを試行
                for vocab_key, vocab_word in vocab_map.items():
                    similarity = SequenceMatcher(None, word_lower, vocab_key).ratio()
                    if similarity >= fuzzy_threshold:
                        matched_vocab = vocab_word
                        break

            if matched_vocab:
                # 優先ワードで置換
                corrected_word = matched_vocab.word
                if original_word[0].isupper():
                    corrected_word = corrected_word.capitalize()

                corrected_words.append(corrected_word)
                if original_word != corrected_word:
                    corrections.append({
                        "original": original_word,
                        "corrected": corrected_word,
                        "word_id": str(matched_vocab.id),
                    })
            else:
                corrected_words.append(original_word)

        return " ".join(corrected_words), corrections


class AutoCorrectionService:
    """自動修正サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_rule(
        self,
        user_id: uuid.UUID,
        name: str,
        rule_type: str,
        pattern: str,
        replacement: str,
        description: Optional[str] = None,
        case_sensitive: bool = False,
        team_id: Optional[uuid.UUID] = None,
        is_shared: bool = False,
    ) -> AutoCorrectionRule:
        """修正ルールを作成"""
        rule = AutoCorrectionRule(
            user_id=user_id,
            team_id=team_id,
            name=name,
            description=description,
            rule_type=rule_type,
            pattern=pattern,
            replacement=replacement,
            case_sensitive=case_sensitive,
            is_shared=is_shared,
        )
        self.db.add(rule)
        await self.db.commit()
        return rule

    async def list_rules(
        self,
        user_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
    ) -> list[AutoCorrectionRule]:
        """修正ルール一覧を取得"""
        conditions = [
            AutoCorrectionRule.is_active == True,
            or_(
                AutoCorrectionRule.user_id == user_id,
                and_(
                    AutoCorrectionRule.team_id == team_id,
                    AutoCorrectionRule.is_shared == True,
                ) if team_id else False,
            ),
        ]

        query = select(AutoCorrectionRule).where(and_(*conditions))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        **kwargs,
    ) -> Optional[AutoCorrectionRule]:
        """修正ルールを更新"""
        query = select(AutoCorrectionRule).where(AutoCorrectionRule.id == rule_id)
        result = await self.db.execute(query)
        rule = result.scalar_one_or_none()

        if not rule:
            return None

        for key, value in kwargs.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)

        await self.db.commit()
        return rule

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        """修正ルールを削除"""
        query = select(AutoCorrectionRule).where(AutoCorrectionRule.id == rule_id)
        result = await self.db.execute(query)
        rule = result.scalar_one_or_none()

        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()
        return True

    def apply_rules(
        self,
        text: str,
        rules: list[AutoCorrectionRule],
    ) -> tuple[str, list[dict]]:
        """修正ルールを適用"""
        corrections = []
        corrected_text = text

        for rule in rules:
            if rule.rule_type == "replace":
                # 単純置換
                flags = 0 if rule.case_sensitive else re.IGNORECASE
                pattern = re.escape(rule.pattern)

                matches = list(re.finditer(pattern, corrected_text, flags))
                if matches:
                    corrected_text = re.sub(pattern, rule.replacement, corrected_text, flags=flags)
                    for match in matches:
                        corrections.append({
                            "rule_id": str(rule.id),
                            "rule_name": rule.name,
                            "original": match.group(),
                            "corrected": rule.replacement,
                            "position": match.start(),
                        })

            elif rule.rule_type == "regex":
                # 正規表現置換
                flags = 0 if rule.case_sensitive else re.IGNORECASE
                try:
                    matches = list(re.finditer(rule.pattern, corrected_text, flags))
                    if matches:
                        corrected_text = re.sub(rule.pattern, rule.replacement, corrected_text, flags=flags)
                        for match in matches:
                            corrections.append({
                                "rule_id": str(rule.id),
                                "rule_name": rule.name,
                                "original": match.group(),
                                "corrected": re.sub(rule.pattern, rule.replacement, match.group(), flags=flags),
                                "position": match.start(),
                            })
                except re.error:
                    # 無効な正規表現の場合はスキップ
                    pass

        return corrected_text, corrections
