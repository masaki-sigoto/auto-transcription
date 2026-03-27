"""高度なユーザー管理APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.services.user_management_service import (
    SessionService,
    MFAService,
    RBACService,
    SCIMService,
    UserRole,
    Permission,
)

router = APIRouter(prefix="/users", tags=["users"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === セッション管理 ===

class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    access_token: str
    refresh_token: str
    expires_at: str


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: LoginRequest,
    req: Request,
):
    """セッションを作成（ログイン）"""
    # 実際の実装ではパスワード検証を行う
    service = SessionService()

    # MFAチェック
    mfa_service = MFAService()
    user_id = "00000000-0000-0000-0000-000000000001"  # 実際はDBから取得

    if mfa_service.is_mfa_enabled(user_id):
        if not request.mfa_code:
            raise HTTPException(
                status_code=401,
                detail={"error": "MFA_REQUIRED", "message": "MFA code is required"},
            )
        if not mfa_service.verify_totp(user_id, request.mfa_code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    session = service.create_session(
        user_id=user_id,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    return SessionResponse(
        session_id=session.id,
        access_token=session.access_token,
        refresh_token=session.refresh_token or "",
        expires_at=session.expires_at.isoformat(),
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/sessions/refresh", response_model=SessionResponse)
async def refresh_session(request: RefreshRequest):
    """セッションをリフレッシュ"""
    service = SessionService()

    session = service.refresh_session(request.refresh_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return SessionResponse(
        session_id=session.id,
        access_token=session.access_token,
        refresh_token=session.refresh_token or "",
        expires_at=session.expires_at.isoformat(),
    )


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セッションを無効化（ログアウト）"""
    service = SessionService()

    if not service.revoke_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "revoked", "session_id": session_id}


@router.delete("/sessions")
async def revoke_all_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """全セッションを無効化"""
    service = SessionService()
    count = service.revoke_all_sessions(str(user_id))

    return {"status": "revoked", "count": count}


@router.get("/sessions")
async def list_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アクティブセッション一覧"""
    service = SessionService()
    sessions = service.get_user_sessions(str(user_id))

    return {
        "sessions": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
            }
            for s in sessions
        ]
    }


# === MFA ===

@router.post("/mfa/setup")
async def setup_mfa(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """MFAをセットアップ"""
    service = MFAService()

    if service.is_mfa_enabled(str(user_id)):
        raise HTTPException(status_code=400, detail="MFA already enabled")

    result = service.setup_totp(str(user_id))

    return {
        "secret": result["secret"],
        "provisioning_uri": result["provisioning_uri"],
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?data={result['provisioning_uri']}",
        "backup_codes": result["backup_codes"],
    }


class MFAVerifyRequest(BaseModel):
    code: str


@router.post("/mfa/enable")
async def enable_mfa(
    request: MFAVerifyRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """MFAを有効化"""
    service = MFAService()

    if not service.enable_mfa(str(user_id), request.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    return {"status": "enabled", "message": "MFA has been enabled"}


@router.post("/mfa/disable")
async def disable_mfa(
    request: MFAVerifyRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """MFAを無効化"""
    service = MFAService()

    if not service.verify_totp(str(user_id), request.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    service.disable_mfa(str(user_id))

    return {"status": "disabled", "message": "MFA has been disabled"}


@router.get("/mfa/status")
async def get_mfa_status(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """MFAステータスを取得"""
    service = MFAService()
    return service.get_mfa_status(str(user_id))


@router.post("/mfa/backup-codes/regenerate")
async def regenerate_backup_codes(
    request: MFAVerifyRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """バックアップコードを再生成"""
    service = MFAService()

    if not service.verify_totp(str(user_id), request.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    codes = service.regenerate_backup_codes(str(user_id))
    if not codes:
        raise HTTPException(status_code=400, detail="MFA not enabled")

    return {"backup_codes": codes}


# === RBAC ===

@router.get("/roles")
async def list_roles(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ロール一覧を取得"""
    service = RBACService()
    return {"roles": service.get_all_roles()}


@router.get("/me/role")
async def get_my_role(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """自分のロールを取得"""
    service = RBACService()
    role = service.get_role(str(user_id))

    return {
        "role": role.value,
        "permissions": [p.value for p in service.get_permissions(str(user_id))],
    }


class AssignRoleRequest(BaseModel):
    user_id: str
    role: str


@router.post("/roles/assign")
async def assign_role(
    request: AssignRoleRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ロールを割り当て（管理者のみ）"""
    service = RBACService()

    if not service.has_permission(str(current_user_id), Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        role = UserRole(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")

    service.assign_role(request.user_id, role)

    return {"status": "assigned", "user_id": request.user_id, "role": role.value}


class PermissionCheckRequest(BaseModel):
    permission: str
    team_id: Optional[str] = None


@router.post("/permissions/check")
async def check_permission(
    request: PermissionCheckRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """権限をチェック"""
    service = RBACService()

    try:
        permission = Permission(request.permission)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid permission")

    has_permission = service.has_permission(
        str(user_id),
        permission,
        request.team_id,
    )

    return {"permission": request.permission, "granted": has_permission}


# === SCIM ===

scim_router = APIRouter(prefix="/scim/v2", tags=["scim"])


class SCIMUserRequest(BaseModel):
    userName: str
    name: dict
    emails: List[dict]
    externalId: Optional[str] = None
    active: bool = True


@scim_router.post("/Users")
async def scim_create_user(request: SCIMUserRequest):
    """SCIMユーザー作成"""
    service = SCIMService()

    email = request.emails[0]["value"] if request.emails else request.userName
    name = request.name.get("formatted", request.userName)

    user = await service.create_user(
        email=email,
        name=name,
        external_id=request.externalId,
    )

    return user


@scim_router.get("/Users/{user_id}")
async def scim_get_user(user_id: str):
    """SCIMユーザー取得"""
    service = SCIMService()

    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@scim_router.put("/Users/{user_id}")
async def scim_update_user(user_id: str, request: SCIMUserRequest):
    """SCIMユーザー更新"""
    service = SCIMService()

    user = await service.update_user(
        user_id,
        {
            "userName": request.userName,
            "name": request.name,
            "emails": request.emails,
            "active": request.active,
        },
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@scim_router.delete("/Users/{user_id}")
async def scim_delete_user(user_id: str):
    """SCIMユーザー削除"""
    service = SCIMService()

    if not await service.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "deleted"}


@scim_router.get("/Users")
async def scim_list_users(
    filter: Optional[str] = None,
    startIndex: int = 1,
    count: int = 100,
):
    """SCIMユーザー一覧"""
    service = SCIMService()

    result = await service.list_users(
        filter_query=filter,
        start_index=startIndex,
        count=count,
    )

    return result


class SCIMGroupRequest(BaseModel):
    displayName: str
    members: Optional[List[dict]] = None


@scim_router.post("/Groups")
async def scim_create_group(request: SCIMGroupRequest):
    """SCIMグループ作成"""
    service = SCIMService()

    members = [m["value"] for m in (request.members or [])]
    group = await service.create_group(
        display_name=request.displayName,
        members=members,
    )

    return group


@scim_router.get("/Groups")
async def scim_list_groups(
    startIndex: int = 1,
    count: int = 100,
):
    """SCIMグループ一覧"""
    service = SCIMService()
    return await service.list_groups(start_index=startIndex, count=count)


# ルーターをマージ
router.include_router(scim_router)
