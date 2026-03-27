import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import io

from app.core.database import get_db
from app.services.audit_service import AuditService, APIKeyService, SecurityPolicyService
from app.models.audit import AuditAction

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def require_admin() -> bool:
    # TODO: 実際の管理者チェックを実装
    return True


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================

class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    user_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[uuid.UUID]
    ip_address: Optional[str]
    status: str
    details: dict
    created_at: str


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


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
    key: APIKeyResponse
    raw_key: str  # 一度だけ表示


class SecurityPolicyResponse(BaseModel):
    password_min_length: int
    password_require_uppercase: bool
    password_require_lowercase: bool
    password_require_numbers: bool
    password_require_special: bool
    password_max_age_days: int
    session_timeout_minutes: int
    max_concurrent_sessions: int
    require_mfa: bool
    ip_whitelist_enabled: bool
    ip_whitelist: list[str]
    data_retention_days: int
    audit_log_retention_days: int


class UpdateSecurityPolicyRequest(BaseModel):
    password_min_length: Optional[int] = None
    password_require_uppercase: Optional[bool] = None
    password_require_lowercase: Optional[bool] = None
    password_require_numbers: Optional[bool] = None
    password_require_special: Optional[bool] = None
    password_max_age_days: Optional[int] = None
    session_timeout_minutes: Optional[int] = None
    max_concurrent_sessions: Optional[int] = None
    require_mfa: Optional[bool] = None
    ip_whitelist_enabled: Optional[bool] = None
    ip_whitelist: Optional[list[str]] = None


# =============================================================================
# 監査ログ
# =============================================================================

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """監査ログ一覧を取得"""
    service = AuditService(db)
    logs, total = await service.list_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        status=status,
        limit=limit,
        offset=offset,
    )

    return AuditLogListResponse(
        logs=[
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_email=log.user.email if log.user else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                status=log.status,
                details=log.details,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-logs/actions")
async def list_audit_actions(
    _: bool = Depends(require_admin),
):
    """利用可能な監査アクション一覧を取得"""
    return {
        "actions": [action.value for action in AuditAction]
    }


@router.get("/audit-logs/export")
async def export_audit_logs(
    start_date: datetime,
    end_date: datetime,
    format: str = Query("json", regex="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """監査ログをエクスポート"""
    service = AuditService(db)
    content = await service.export_logs(start_date, end_date, format)

    if format == "json":
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{start_date.date()}_{end_date.date()}.json"}
        )
    else:
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_logs_{start_date.date()}_{end_date.date()}.csv"}
        )


@router.get("/audit-logs/security-events", response_model=list[AuditLogResponse])
async def get_security_events(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """セキュリティ関連イベントを取得"""
    service = AuditService(db)
    logs = await service.get_security_events(days)

    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=log.user.email if log.user else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            status=log.status,
            details=log.details,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/users/{target_user_id}/activity", response_model=list[AuditLogResponse])
async def get_user_activity(
    target_user_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """ユーザーのアクティビティを取得"""
    service = AuditService(db)
    logs = await service.get_user_activity(target_user_id, days)

    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            status=log.status,
            details=log.details,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


# =============================================================================
# APIキー管理
# =============================================================================

@router.post("/api-keys", response_model=APIKeyCreatedResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    _: bool = Depends(require_admin),
    http_request: Request = None,
):
    """APIキーを作成"""
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
        key=APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            scopes=api_key.scopes,
            expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
            last_used_at=None,
            created_at=api_key.created_at.isoformat(),
        ),
        raw_key=raw_key,
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
            scopes=key.scopes,
            expires_at=key.expires_at.isoformat() if key.expires_at else None,
            last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
            created_at=key.created_at.isoformat(),
        )
        for key in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    http_request: Request = None,
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
# セキュリティポリシー
# =============================================================================

@router.get("/security-policy", response_model=SecurityPolicyResponse)
async def get_security_policy(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """セキュリティポリシーを取得"""
    service = SecurityPolicyService(db)
    policy = await service.get_or_create_default()

    return SecurityPolicyResponse(
        password_min_length=int(policy.password_min_length),
        password_require_uppercase=policy.password_require_uppercase == "true",
        password_require_lowercase=policy.password_require_lowercase == "true",
        password_require_numbers=policy.password_require_numbers == "true",
        password_require_special=policy.password_require_special == "true",
        password_max_age_days=int(policy.password_max_age_days),
        session_timeout_minutes=int(policy.session_timeout_minutes),
        max_concurrent_sessions=int(policy.max_concurrent_sessions),
        require_mfa=policy.require_mfa == "true",
        ip_whitelist_enabled=policy.ip_whitelist_enabled == "true",
        ip_whitelist=policy.ip_whitelist or [],
        data_retention_days=int(policy.data_retention_days),
        audit_log_retention_days=int(policy.audit_log_retention_days),
    )


@router.patch("/security-policy", response_model=SecurityPolicyResponse)
async def update_security_policy(
    request: UpdateSecurityPolicyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    _: bool = Depends(require_admin),
    http_request: Request = None,
):
    """セキュリティポリシーを更新"""
    service = SecurityPolicyService(db)
    audit_service = AuditService(db)

    # 現在の値を取得
    old_policy = await service.get_or_create_default()
    old_values = {
        "password_min_length": old_policy.password_min_length,
        "require_mfa": old_policy.require_mfa,
    }

    # 更新データを準備
    update_data = {}
    if request.password_min_length is not None:
        update_data["password_min_length"] = request.password_min_length
    if request.password_require_uppercase is not None:
        update_data["password_require_uppercase"] = "true" if request.password_require_uppercase else "false"
    if request.password_require_lowercase is not None:
        update_data["password_require_lowercase"] = "true" if request.password_require_lowercase else "false"
    if request.password_require_numbers is not None:
        update_data["password_require_numbers"] = "true" if request.password_require_numbers else "false"
    if request.password_require_special is not None:
        update_data["password_require_special"] = "true" if request.password_require_special else "false"
    if request.password_max_age_days is not None:
        update_data["password_max_age_days"] = request.password_max_age_days
    if request.session_timeout_minutes is not None:
        update_data["session_timeout_minutes"] = request.session_timeout_minutes
    if request.max_concurrent_sessions is not None:
        update_data["max_concurrent_sessions"] = request.max_concurrent_sessions
    if request.require_mfa is not None:
        update_data["require_mfa"] = "true" if request.require_mfa else "false"
    if request.ip_whitelist_enabled is not None:
        update_data["ip_whitelist_enabled"] = "true" if request.ip_whitelist_enabled else "false"
    if request.ip_whitelist is not None:
        update_data["ip_whitelist"] = request.ip_whitelist

    policy = await service.update_policy(**update_data)

    # 監査ログ
    await audit_service.log(
        action=AuditAction.SETTINGS_CHANGED.value,
        user_id=user_id,
        resource_type="security_policy",
        details={"changes": update_data},
        old_value=old_values,
        new_value=update_data,
        request=http_request,
    )

    return SecurityPolicyResponse(
        password_min_length=int(policy.password_min_length),
        password_require_uppercase=policy.password_require_uppercase == "true",
        password_require_lowercase=policy.password_require_lowercase == "true",
        password_require_numbers=policy.password_require_numbers == "true",
        password_require_special=policy.password_require_special == "true",
        password_max_age_days=int(policy.password_max_age_days),
        session_timeout_minutes=int(policy.session_timeout_minutes),
        max_concurrent_sessions=int(policy.max_concurrent_sessions),
        require_mfa=policy.require_mfa == "true",
        ip_whitelist_enabled=policy.ip_whitelist_enabled == "true",
        ip_whitelist=policy.ip_whitelist or [],
        data_retention_days=int(policy.data_retention_days),
        audit_log_retention_days=int(policy.audit_log_retention_days),
    )
