import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import uuid

from app.main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.models.transcription import Transcription, TranscriptionSegment, Speaker


# テスト用のインメモリSQLiteデータベース
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """イベントループを作成"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """テスト用データベースエンジンを作成"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """テスト用データベースセッションを作成"""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """テスト用HTTPクライアントを作成"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """テスト用ユーザーを作成"""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_transcription(db_session: AsyncSession, test_user: User) -> Transcription:
    """テスト用文字起こしを作成"""
    transcription = Transcription(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="テスト文字起こし",
        status="completed",
        audio_duration_sec=120,
        file_path="test/audio.mp3",
        file_size=1024000,
    )
    db_session.add(transcription)
    await db_session.commit()
    await db_session.refresh(transcription)
    return transcription


@pytest_asyncio.fixture
async def test_transcription_with_segments(
    db_session: AsyncSession,
    test_transcription: Transcription,
) -> Transcription:
    """セグメント付きの文字起こしを作成"""
    # 話者を作成
    speaker1 = Speaker(
        transcription_id=test_transcription.id,
        label="話者A",
    )
    speaker2 = Speaker(
        transcription_id=test_transcription.id,
        label="話者B",
    )
    db_session.add_all([speaker1, speaker2])
    await db_session.flush()

    # セグメントを作成
    segments = [
        TranscriptionSegment(
            transcription_id=test_transcription.id,
            start_time_ms=0,
            end_time_ms=5000,
            text="こんにちは、本日はよろしくお願いします。",
            speaker_id=speaker1.id,
            confidence=0.95,
        ),
        TranscriptionSegment(
            transcription_id=test_transcription.id,
            start_time_ms=5000,
            end_time_ms=10000,
            text="はい、よろしくお願いします。",
            speaker_id=speaker2.id,
            confidence=0.92,
        ),
        TranscriptionSegment(
            transcription_id=test_transcription.id,
            start_time_ms=10000,
            end_time_ms=20000,
            text="今日の議題について説明させていただきます。",
            speaker_id=speaker1.id,
            confidence=0.88,
        ),
    ]
    db_session.add_all(segments)
    await db_session.commit()

    await db_session.refresh(test_transcription)
    return test_transcription


# テスト用のモック
class MockTranscriptionEngine:
    """文字起こしエンジンのモック"""

    async def transcribe(self, audio_path: str, language: str = "ja"):
        return [
            {
                "start_time_ms": 0,
                "end_time_ms": 5000,
                "text": "テスト文字起こし結果です。",
                "confidence": 0.95,
            }
        ]


class MockLLMCorrector:
    """LLM補正のモック"""

    async def correct(self, text: str) -> str:
        return text


class MockStorageClient:
    """ストレージクライアントのモック"""

    async def upload(self, file_path: str, content: bytes) -> str:
        return f"https://storage.example.com/{file_path}"

    async def download(self, file_path: str) -> bytes:
        return b"mock audio content"

    async def delete(self, file_path: str) -> bool:
        return True


class MockCacheService:
    """キャッシュサービスのモック"""

    def __init__(self):
        self._cache = {}

    async def get(self, key: str):
        return self._cache.get(key)

    async def set(self, key: str, value, ttl: int = 300):
        self._cache[key] = value

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False


class MockOpenAIClient:
    """OpenAIクライアントのモック"""

    async def chat_completion(self, messages: list, model: str = "gpt-4o"):
        return {"content": "モックAIレスポンス"}

    async def embeddings(self, text: str):
        return [0.1] * 1536  # OpenAI embeddingの次元数


@pytest.fixture
def mock_cache_service():
    return MockCacheService()


@pytest.fixture
def mock_storage_client():
    return MockStorageClient()


@pytest.fixture
def mock_openai_client():
    return MockOpenAIClient()


@pytest.fixture
def sample_audio_file(tmp_path):
    """サンプル音声ファイル"""
    audio_path = tmp_path / "test_audio.wav"
    # 簡易WAVヘッダー
    audio_path.write_bytes(b"RIFF" + b"\x00" * 100)
    return str(audio_path)


@pytest.fixture
def auth_headers():
    """認証ヘッダー"""
    import jwt
    from datetime import datetime
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "exp": datetime.utcnow().timestamp() + 3600
        },
        "test-secret-key",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
