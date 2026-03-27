import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.services.audit_service import APIKeyService, AuditService
from app.models.audit import AuditAction

router = APIRouter(prefix="/developer", tags=["developer"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# APIキー認証
# =============================================================================

async def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """APIキーを検証"""
    service = APIKeyService(db)
    api_key = await service.validate_key(x_api_key)

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "API-Key"},
        )

    return api_key


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================

class CreateAPIKeyRequest(BaseModel):
    name: str
    scopes: list[str] = []
    expires_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: Optional[str]
    last_used_at: Optional[str]
    created_at: str


class APIKeyCreatedResponse(BaseModel):
    api_key: APIKeyResponse
    secret_key: str  # 一度だけ表示


class WebhookEndpointRequest(BaseModel):
    url: str
    events: list[str]
    secret: Optional[str] = None
    is_active: bool = True


class RateLimitInfo(BaseModel):
    requests_per_minute: int
    requests_remaining: int
    reset_at: str


class APIUsageResponse(BaseModel):
    total_requests: int
    requests_today: int
    requests_this_month: int
    rate_limit: RateLimitInfo


# =============================================================================
# APIキー管理
# =============================================================================

@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(
    request: CreateAPIKeyRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """新しいAPIキーを作成"""
    key_service = APIKeyService(db)
    audit_service = AuditService(db)

    api_key, raw_key = await key_service.create_key(
        user_id=user_id,
        name=request.name,
        scopes=request.scopes,
        expires_days=request.expires_days,
    )

    # 監査ログ
    await audit_service.log(
        action=AuditAction.API_KEY_CREATED.value,
        user_id=user_id,
        resource_type="api_key",
        resource_id=api_key.id,
        details={"name": request.name, "scopes": request.scopes},
        request=http_request,
    )

    return APIKeyCreatedResponse(
        api_key=APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            scopes=api_key.scopes or [],
            expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
            last_used_at=None,
            created_at=api_key.created_at.isoformat(),
        ),
        secret_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """APIキー一覧を取得"""
    service = APIKeyService(db)
    keys = await service.list_keys(user_id)

    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes or [],
            expires_at=key.expires_at.isoformat() if key.expires_at else None,
            last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
            created_at=key.created_at.isoformat(),
        )
        for key in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """APIキーを取り消し"""
    key_service = APIKeyService(db)
    audit_service = AuditService(db)

    if not await key_service.revoke_key(key_id, user_id):
        raise HTTPException(status_code=404, detail="API key not found")

    # 監査ログ
    await audit_service.log(
        action=AuditAction.API_KEY_REVOKED.value,
        user_id=user_id,
        resource_type="api_key",
        resource_id=key_id,
        request=http_request,
    )


# =============================================================================
# API使用量
# =============================================================================

@router.get("/usage", response_model=APIUsageResponse)
async def get_api_usage(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """API使用量を取得"""
    # TODO: 実際のレート制限実装
    return APIUsageResponse(
        total_requests=1000,
        requests_today=50,
        requests_this_month=500,
        rate_limit=RateLimitInfo(
            requests_per_minute=60,
            requests_remaining=55,
            reset_at=(datetime.utcnow() + timedelta(seconds=30)).isoformat(),
        ),
    )


# =============================================================================
# APIドキュメント情報
# =============================================================================

@router.get("/docs/info")
async def get_api_info():
    """API情報を取得"""
    return {
        "name": "VoiceScribe API",
        "version": "1.0.0",
        "description": "AIを活用した高精度な音声文字起こしAPI",
        "base_url": "/api/v1",
        "authentication": {
            "type": "API Key",
            "header": "X-API-Key",
            "description": "APIキーをリクエストヘッダーに含めてください",
        },
        "rate_limits": {
            "free": {
                "requests_per_minute": 10,
                "requests_per_day": 100,
                "max_file_size_mb": 25,
                "max_duration_minutes": 30,
            },
            "pro": {
                "requests_per_minute": 60,
                "requests_per_day": 1000,
                "max_file_size_mb": 500,
                "max_duration_minutes": 180,
            },
            "enterprise": {
                "requests_per_minute": 300,
                "requests_per_day": 10000,
                "max_file_size_mb": 2000,
                "max_duration_minutes": 480,
            },
        },
        "endpoints": {
            "transcription": {
                "create": "POST /api/v1/transcriptions",
                "get": "GET /api/v1/transcriptions/{id}",
                "list": "GET /api/v1/transcriptions",
                "delete": "DELETE /api/v1/transcriptions/{id}",
            },
            "upload": {
                "upload_file": "POST /api/v1/upload",
                "upload_url": "POST /api/v1/upload/url",
            },
            "ai": {
                "meeting_minutes": "POST /api/v1/ai/transcriptions/{id}/meeting-minutes",
                "summary": "POST /api/v1/ai/transcriptions/{id}/content-summary",
                "chapters": "POST /api/v1/ai/transcriptions/{id}/chapters",
            },
            "analytics": {
                "usage": "GET /api/v1/analytics/usage/summary",
                "transcription": "GET /api/v1/analytics/transcriptions/{id}/analytics",
            },
        },
        "webhooks": {
            "events": [
                "transcription.created",
                "transcription.completed",
                "transcription.failed",
                "transcription.updated",
            ],
            "signature_header": "X-Webhook-Signature",
            "signature_algorithm": "HMAC-SHA256",
        },
    }


@router.get("/docs/scopes")
async def get_api_scopes():
    """利用可能なAPIスコープを取得"""
    return {
        "scopes": [
            {
                "name": "transcriptions:read",
                "description": "文字起こしの読み取り",
            },
            {
                "name": "transcriptions:write",
                "description": "文字起こしの作成・更新・削除",
            },
            {
                "name": "upload",
                "description": "ファイルのアップロード",
            },
            {
                "name": "ai",
                "description": "AI機能（要約、議事録生成など）の使用",
            },
            {
                "name": "analytics:read",
                "description": "分析データの読み取り",
            },
            {
                "name": "webhooks",
                "description": "Webhookの管理",
            },
            {
                "name": "admin",
                "description": "管理者機能へのアクセス",
            },
        ],
    }


# =============================================================================
# サンプルコード
# =============================================================================

@router.get("/docs/examples")
async def get_code_examples():
    """サンプルコードを取得"""
    return {
        "python": {
            "upload_file": '''
import requests

API_KEY = "your-api-key"
API_URL = "https://api.voicescribe.app/api/v1"

# ファイルをアップロード
with open("audio.mp3", "rb") as f:
    response = requests.post(
        f"{API_URL}/upload",
        headers={"X-API-Key": API_KEY},
        files={"file": f},
        data={"language": "ja"}
    )
    result = response.json()
    transcription_id = result["id"]

print(f"Transcription ID: {transcription_id}")
''',
            "get_transcription": '''
import requests

API_KEY = "your-api-key"
API_URL = "https://api.voicescribe.app/api/v1"
transcription_id = "your-transcription-id"

response = requests.get(
    f"{API_URL}/transcriptions/{transcription_id}",
    headers={"X-API-Key": API_KEY}
)
transcription = response.json()

print(f"Title: {transcription['title']}")
print(f"Status: {transcription['status']}")
for segment in transcription["segments"]:
    print(f"[{segment['start_time_ms']}] {segment['text']}")
''',
            "generate_summary": '''
import requests

API_KEY = "your-api-key"
API_URL = "https://api.voicescribe.app/api/v1"
transcription_id = "your-transcription-id"

response = requests.post(
    f"{API_URL}/ai/transcriptions/{transcription_id}/meeting-minutes",
    headers={"X-API-Key": API_KEY}
)
minutes = response.json()

print(f"Title: {minutes['title']}")
print(f"Summary: {minutes['summary']}")
print("Action Items:")
for item in minutes["action_items"]:
    print(f"  - {item['task']} (@{item['assignee']})")
''',
        },
        "javascript": {
            "upload_file": '''
const API_KEY = "your-api-key";
const API_URL = "https://api.voicescribe.app/api/v1";

const formData = new FormData();
formData.append("file", audioFile);
formData.append("language", "ja");

const response = await fetch(`${API_URL}/upload`, {
  method: "POST",
  headers: {
    "X-API-Key": API_KEY,
  },
  body: formData,
});

const result = await response.json();
console.log("Transcription ID:", result.id);
''',
            "get_transcription": '''
const API_KEY = "your-api-key";
const API_URL = "https://api.voicescribe.app/api/v1";
const transcriptionId = "your-transcription-id";

const response = await fetch(
  `${API_URL}/transcriptions/${transcriptionId}`,
  {
    headers: {
      "X-API-Key": API_KEY,
    },
  }
);

const transcription = await response.json();
console.log("Title:", transcription.title);
console.log("Status:", transcription.status);
''',
        },
        "curl": {
            "upload_file": '''
curl -X POST "https://api.voicescribe.app/api/v1/upload" \\
  -H "X-API-Key: your-api-key" \\
  -F "file=@audio.mp3" \\
  -F "language=ja"
''',
            "get_transcription": '''
curl -X GET "https://api.voicescribe.app/api/v1/transcriptions/{id}" \\
  -H "X-API-Key: your-api-key"
''',
            "list_transcriptions": '''
curl -X GET "https://api.voicescribe.app/api/v1/transcriptions" \\
  -H "X-API-Key: your-api-key"
''',
        },
    }
