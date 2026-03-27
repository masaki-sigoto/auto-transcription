# 自動文字起こしツール 開発者ガイド

## 目次

1. [開発環境のセットアップ](#開発環境のセットアップ)
2. [プロジェクト構造](#プロジェクト構造)
3. [バックエンド開発](#バックエンド開発)
4. [フロントエンド開発](#フロントエンド開発)
5. [テスト](#テスト)
6. [コーディング規約](#コーディング規約)
7. [API設計](#api設計)
8. [データベース](#データベース)

---

## 開発環境のセットアップ

### 必要なツール

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Poetry (Python依存管理)
- pnpm or npm (Node.js依存管理)

### クイックスタート

```bash
# リポジトリのクローン
git clone https://github.com/your-org/transcription-app.git
cd transcription-app

# Docker Composeで起動
docker-compose up -d

# バックエンドのセットアップ
cd backend
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload

# フロントエンドのセットアップ（別ターミナル）
cd frontend
npm install
npm run dev
```

### 環境変数

`.env.local` ファイルを作成:

```env
# Backend
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/transcription
REDIS_URL=redis://localhost:6379
JWT_SECRET_KEY=your-dev-secret-key
OPENAI_API_KEY=sk-your-api-key

# Frontend
VITE_API_URL=http://localhost:8000
```

---

## プロジェクト構造

```
transcription-app/
├── backend/
│   ├── app/
│   │   ├── api/           # APIエンドポイント
│   │   │   └── v1/
│   │   ├── core/          # 設定・認証・DB
│   │   ├── models/        # SQLAlchemyモデル
│   │   ├── schemas/       # Pydanticスキーマ
│   │   ├── services/      # ビジネスロジック
│   │   └── main.py        # アプリケーションエントリ
│   ├── tests/             # テスト
│   ├── alembic/           # マイグレーション
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/    # UIコンポーネント
│   │   ├── pages/         # ページコンポーネント
│   │   ├── hooks/         # カスタムフック
│   │   ├── lib/           # ユーティリティ
│   │   ├── stores/        # 状態管理
│   │   └── App.tsx
│   ├── e2e/               # E2Eテスト
│   └── package.json
├── deploy/
│   ├── kubernetes/        # K8sマニフェスト
│   └── terraform/         # インフラ定義
└── docs/                  # ドキュメント
```

---

## バックエンド開発

### 新しいAPIエンドポイントの追加

1. **スキーマを定義** (`app/schemas/`)

```python
# app/schemas/example.py
from pydantic import BaseModel
from uuid import UUID

class ExampleCreate(BaseModel):
    name: str
    description: str | None = None

class ExampleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None

    class Config:
        from_attributes = True
```

2. **モデルを定義** (`app/models/`)

```python
# app/models/example.py
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base

class Example(Base):
    __tablename__ = "examples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
```

3. **サービスを実装** (`app/services/`)

```python
# app/services/example_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.example import Example
from app.schemas.example import ExampleCreate

class ExampleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: ExampleCreate) -> Example:
        example = Example(**data.model_dump())
        self.db.add(example)
        await self.db.commit()
        await self.db.refresh(example)
        return example

    async def get_by_id(self, id: UUID) -> Example | None:
        result = await self.db.execute(
            select(Example).where(Example.id == id)
        )
        return result.scalar_one_or_none()
```

4. **APIルーターを作成** (`app/api/v1/`)

```python
# app/api/v1/example.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.schemas.example import ExampleCreate, ExampleResponse
from app.services.example_service import ExampleService

router = APIRouter(prefix="/examples", tags=["examples"])

@router.post("", response_model=ExampleResponse, status_code=201)
async def create_example(
    data: ExampleCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ExampleService(db)
    return await service.create(data)

@router.get("/{id}", response_model=ExampleResponse)
async def get_example(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ExampleService(db)
    example = await service.get_by_id(id)
    if not example:
        raise HTTPException(status_code=404, detail="Not found")
    return example
```

5. **ルーターを登録** (`app/api/v1/router.py`)

```python
from app.api.v1.example import router as example_router

api_router.include_router(example_router)
```

### マイグレーション

```bash
# 新しいマイグレーションを作成
poetry run alembic revision --autogenerate -m "Add example table"

# マイグレーションを適用
poetry run alembic upgrade head

# ロールバック
poetry run alembic downgrade -1
```

---

## フロントエンド開発

### 新しいページの追加

1. **ページコンポーネントを作成**

```tsx
// src/pages/Example.tsx
import { useState, useEffect } from 'react';
import { useApi } from '@/hooks/useApi';

interface Example {
  id: string;
  name: string;
  description?: string;
}

export default function ExamplePage() {
  const [examples, setExamples] = useState<Example[]>([]);
  const api = useApi();

  useEffect(() => {
    const fetchExamples = async () => {
      const data = await api.get<Example[]>('/examples');
      setExamples(data);
    };
    fetchExamples();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Examples</h1>
      <ul>
        {examples.map((example) => (
          <li key={example.id}>{example.name}</li>
        ))}
      </ul>
    </div>
  );
}
```

2. **ルートを追加** (`src/App.tsx`)

```tsx
import ExamplePage from '@/pages/Example';

// Routes内に追加
<Route path="/examples" element={<ExamplePage />} />
```

### カスタムフックの作成

```tsx
// src/hooks/useExamples.ts
import { useState, useCallback } from 'react';
import { useApi } from './useApi';

export function useExamples() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const api = useApi();

  const create = useCallback(async (data: { name: string }) => {
    setLoading(true);
    try {
      const result = await api.post('/examples', data);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [api]);

  return { create, loading, error };
}
```

---

## テスト

### バックエンドテスト

```bash
# 全テスト実行
poetry run pytest

# カバレッジ付き
poetry run pytest --cov=app --cov-report=html

# 特定のテスト
poetry run pytest tests/test_transcriptions.py -v

# マーカーでフィルタ
poetry run pytest -m "not slow"
```

**テストの書き方**

```python
# tests/test_example.py
import pytest
from httpx import AsyncClient

class TestExampleAPI:
    @pytest.mark.asyncio
    async def test_create_example(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/examples",
            json={"name": "Test Example"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test Example"
```

### フロントエンドテスト

```bash
# ユニットテスト
npm run test

# E2Eテスト
npm run test:e2e

# 特定のブラウザ
npx playwright test --project=chromium
```

**E2Eテストの書き方**

```typescript
// e2e/example.spec.ts
import { test, expect } from '@playwright/test';

test('should create example', async ({ page }) => {
  await page.goto('/examples/new');
  await page.fill('[data-testid="name-input"]', 'Test');
  await page.click('[data-testid="submit-button"]');
  await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
});
```

---

## コーディング規約

### Python

- **フォーマッター**: Ruff
- **リンター**: Ruff
- **型チェック**: mypy

```bash
# フォーマット
poetry run ruff format .

# リント
poetry run ruff check .

# 型チェック
poetry run mypy app
```

### TypeScript

- **フォーマッター**: Prettier
- **リンター**: ESLint

```bash
# フォーマット
npm run format

# リント
npm run lint
```

### コミットメッセージ

Conventional Commits形式を使用:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type一覧**

- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: フォーマット
- `refactor`: リファクタリング
- `test`: テスト
- `chore`: その他

---

## API設計

### RESTful設計原則

1. **リソース指向のURL**
   - ✓ `GET /transcriptions`
   - ✗ `GET /getTranscriptions`

2. **適切なHTTPメソッド**
   - `GET`: 取得
   - `POST`: 作成
   - `PATCH`: 部分更新
   - `DELETE`: 削除

3. **ステータスコード**
   - `200`: 成功
   - `201`: 作成完了
   - `204`: 削除完了
   - `400`: リクエスト不正
   - `401`: 認証エラー
   - `403`: 権限エラー
   - `404`: 見つからない
   - `500`: サーバーエラー

### エラーレスポンス形式

```json
{
  "error": "validation_error",
  "message": "Invalid input data",
  "details": {
    "name": ["This field is required"]
  }
}
```

---

## データベース

### 命名規約

- テーブル名: スネークケース複数形 (`transcriptions`)
- カラム名: スネークケース (`created_at`)
- インデックス: `idx_<table>_<columns>`
- 外部キー: `fk_<table>_<ref_table>`

### インデックス設計

```python
# 頻繁に検索されるカラムにインデックス
__table_args__ = (
    Index('idx_transcriptions_user_id', 'user_id'),
    Index('idx_transcriptions_status', 'status'),
    Index('idx_transcriptions_created_at', 'created_at'),
)
```

### N+1問題の回避

```python
# Bad
transcriptions = await db.execute(select(Transcription))
for t in transcriptions:
    print(t.user.name)  # N+1クエリ発生

# Good
transcriptions = await db.execute(
    select(Transcription).options(selectinload(Transcription.user))
)
```

---

## トラブルシューティング

### よくある問題

**1. マイグレーションエラー**

```bash
# 現在のバージョン確認
poetry run alembic current

# リビジョン履歴確認
poetry run alembic history
```

**2. 型エラー**

```bash
# mypyキャッシュをクリア
rm -rf .mypy_cache
poetry run mypy app
```

**3. テスト失敗**

```bash
# テストDBをリセット
dropdb test_db
createdb test_db
poetry run pytest
```
