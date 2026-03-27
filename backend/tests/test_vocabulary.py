import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.vocabulary import VocabularyDictionary, VocabularyWord, AutoCorrectionRule
from app.services.vocabulary_service import VocabularyService, AutoCorrectionService


class TestVocabularyAPI:
    """辞書APIのテスト"""

    @pytest.mark.asyncio
    async def test_create_dictionary(self, client: AsyncClient, test_user):
        """辞書を作成"""
        response = await client.post(
            "/api/v1/vocabulary/dictionaries",
            json={
                "name": "技術用語辞書",
                "description": "技術用語のカスタム辞書",
                "language": "ja",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "技術用語辞書"
        assert data["language"] == "ja"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_dictionaries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """辞書一覧を取得"""
        # 辞書を作成
        dict1 = VocabularyDictionary(
            user_id=test_user.id,
            name="辞書1",
            language="ja",
        )
        dict2 = VocabularyDictionary(
            user_id=test_user.id,
            name="辞書2",
            language="en",
        )
        db_session.add_all([dict1, dict2])
        await db_session.commit()

        response = await client.get("/api/v1/vocabulary/dictionaries")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_add_word_to_dictionary(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """辞書に単語を追加"""
        # 辞書を作成
        dictionary = VocabularyDictionary(
            user_id=test_user.id,
            name="テスト辞書",
            language="ja",
        )
        db_session.add(dictionary)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/vocabulary/dictionaries/{dictionary.id}/words",
            json={
                "word": "クラウドネイティブ",
                "reading": "くらうどねいてぃぶ",
                "part_of_speech": "名詞",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["word"] == "クラウドネイティブ"
        assert data["reading"] == "くらうどねいてぃぶ"

    @pytest.mark.asyncio
    async def test_list_words(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """単語一覧を取得"""
        dictionary = VocabularyDictionary(
            user_id=test_user.id,
            name="単語テスト辞書",
            language="ja",
        )
        db_session.add(dictionary)
        await db_session.flush()

        words = [
            VocabularyWord(dictionary_id=dictionary.id, word="単語1"),
            VocabularyWord(dictionary_id=dictionary.id, word="単語2"),
            VocabularyWord(dictionary_id=dictionary.id, word="単語3"),
        ]
        db_session.add_all(words)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/vocabulary/dictionaries/{dictionary.id}/words"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_delete_word(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """単語を削除"""
        dictionary = VocabularyDictionary(
            user_id=test_user.id,
            name="削除テスト辞書",
            language="ja",
        )
        db_session.add(dictionary)
        await db_session.flush()

        word = VocabularyWord(dictionary_id=dictionary.id, word="削除予定単語")
        db_session.add(word)
        await db_session.commit()

        response = await client.delete(
            f"/api/v1/vocabulary/dictionaries/{dictionary.id}/words/{word.id}"
        )
        assert response.status_code == 204


class TestAutoCorrectionAPI:
    """自動補正APIのテスト"""

    @pytest.mark.asyncio
    async def test_create_correction_rule(
        self,
        client: AsyncClient,
        test_user,
    ):
        """補正ルールを作成"""
        response = await client.post(
            "/api/v1/vocabulary/corrections",
            json={
                "pattern": "えーと",
                "replacement": "",
                "rule_type": "filler",
                "description": "フィラー除去",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["pattern"] == "えーと"
        assert data["rule_type"] == "filler"

    @pytest.mark.asyncio
    async def test_list_correction_rules(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """補正ルール一覧を取得"""
        rules = [
            AutoCorrectionRule(
                user_id=test_user.id,
                pattern="あのー",
                replacement="",
                rule_type="filler",
            ),
            AutoCorrectionRule(
                user_id=test_user.id,
                pattern="御社",
                replacement="貴社",
                rule_type="custom",
            ),
        ]
        db_session.add_all(rules)
        await db_session.commit()

        response = await client.get("/api/v1/vocabulary/corrections")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_apply_corrections(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        """補正を適用"""
        rule = AutoCorrectionRule(
            user_id=test_user.id,
            pattern="えーと",
            replacement="",
            rule_type="filler",
            is_active=True,
        )
        db_session.add(rule)
        await db_session.commit()

        response = await client.post(
            "/api/v1/vocabulary/corrections/apply",
            json={
                "text": "えーと、今日の議題についてえーと説明します。",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "えーと" not in data["corrected_text"]


class TestVocabularyService:
    """VocabularyServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_search_words(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """単語を検索"""
        dictionary = VocabularyDictionary(
            user_id=test_user.id,
            name="検索テスト辞書",
            language="ja",
        )
        db_session.add(dictionary)
        await db_session.flush()

        words = [
            VocabularyWord(dictionary_id=dictionary.id, word="マイクロサービス"),
            VocabularyWord(dictionary_id=dictionary.id, word="マイクロソフト"),
            VocabularyWord(dictionary_id=dictionary.id, word="データベース"),
        ]
        db_session.add_all(words)
        await db_session.commit()

        service = VocabularyService(db_session)
        results = await service.search_words(
            user_id=test_user.id,
            query="マイクロ",
        )

        assert len(results) == 2
        assert all("マイクロ" in word.word for word in results)

    @pytest.mark.asyncio
    async def test_import_words(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """単語をインポート"""
        dictionary = VocabularyDictionary(
            user_id=test_user.id,
            name="インポートテスト辞書",
            language="ja",
        )
        db_session.add(dictionary)
        await db_session.commit()

        service = VocabularyService(db_session)
        words_data = [
            {"word": "単語A", "reading": "たんごえー"},
            {"word": "単語B", "reading": "たんごびー"},
            {"word": "単語C", "reading": "たんごしー"},
        ]

        imported = await service.import_words(
            dictionary_id=dictionary.id,
            words=words_data,
        )

        assert imported == 3


class TestAutoCorrectionService:
    """AutoCorrectionServiceの単体テスト"""

    @pytest.mark.asyncio
    async def test_apply_all_rules(
        self,
        db_session: AsyncSession,
        test_user,
    ):
        """すべてのルールを適用"""
        rules = [
            AutoCorrectionRule(
                user_id=test_user.id,
                pattern="えーと",
                replacement="",
                rule_type="filler",
                is_active=True,
            ),
            AutoCorrectionRule(
                user_id=test_user.id,
                pattern="あのー",
                replacement="",
                rule_type="filler",
                is_active=True,
            ),
        ]
        db_session.add_all(rules)
        await db_session.commit()

        service = AutoCorrectionService(db_session)
        text = "えーと、あのー、今日はよろしくお願いします。"

        corrected = await service.apply_corrections(
            user_id=test_user.id,
            text=text,
        )

        assert "えーと" not in corrected
        assert "あのー" not in corrected
        assert "今日はよろしくお願いします" in corrected
