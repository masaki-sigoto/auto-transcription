"""認証APIエンドポイント"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


# ==================
# リクエスト/レスポンススキーマ
# ==================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30分


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    avatar_url: Optional[str]
    plan: str
    is_verified: bool


# ==================
# 登録・ログイン
# ==================

@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """ユーザー登録"""
    auth_service = AuthService(db)

    try:
        user = await auth_service.register(
            email=request.email,
            password=request.password,
            name=request.name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 登録後すぐにログイン状態にする
    result = await auth_service.login(request.email, request.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration succeeded but login failed",
        )

    _, access_token, refresh_token = result

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """ログイン"""
    auth_service = AuthService(db)

    # デバイス情報を取得
    device_info = req.headers.get("User-Agent", "unknown")

    result = await auth_service.login(
        email=request.email,
        password=request.password,
        device_info=device_info,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _, access_token, refresh_token = result

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/logout")
async def logout(
    request: RefreshRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ログアウト"""
    auth_service = AuthService(db)
    await auth_service.logout(user.id, request.refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """全デバイスからログアウト"""
    auth_service = AuthService(db)
    count = await auth_service.logout_all(user.id)
    return {"message": f"Logged out from {count} devices"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """トークンをリフレッシュ"""
    auth_service = AuthService(db)

    result = await auth_service.refresh_access_token(request.refresh_token)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, refresh_token = result

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ==================
# ユーザー情報
# ==================

@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
):
    """現在のユーザー情報を取得"""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        plan=user.plan,
        is_verified=user.is_verified,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ユーザー情報を更新"""
    if name is not None:
        user.name = name
    if avatar_url is not None:
        user.avatar_url = avatar_url

    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        plan=user.plan,
        is_verified=user.is_verified,
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """パスワード変更"""
    auth_service = AuthService(db)

    success = await auth_service.change_password(
        user_id=user.id,
        old_password=request.old_password,
        new_password=request.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password",
        )

    return {"message": "Password changed successfully"}


# ==================
# OAuth - Google
# ==================

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")


@router.get("/google")
async def google_login():
    """Google OAuth開始"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Google OAuthコールバック"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    # アクセストークンを取得
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get access token from Google",
            )

        tokens = token_response.json()
        google_access_token = tokens["access_token"]

        # ユーザー情報を取得
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )

        userinfo = userinfo_response.json()

    # ログイン/登録
    auth_service = AuthService(db)
    device_info = req.headers.get("User-Agent", "unknown")

    user, access_token, refresh_token = await auth_service.oauth_login(
        provider="google",
        oauth_id=userinfo["id"],
        email=userinfo["email"],
        name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
        device_info=device_info,
    )

    # フロントエンドにリダイレクト（トークンをURLパラメータで渡す）
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url = f"{frontend_url}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"

    return RedirectResponse(redirect_url)


# ==================
# OAuth - GitHub
# ==================

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/api/v1/auth/github/callback")


@router.get("/github")
async def github_login():
    """GitHub OAuth開始"""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured",
        )

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": "user:email",
    }
    url = "https://github.com/login/oauth/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
    code: str,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """GitHub OAuthコールバック"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured",
        )

    async with httpx.AsyncClient() as client:
        # アクセストークンを取得
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "code": code,
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get access token from GitHub",
            )

        tokens = token_response.json()
        github_access_token = tokens["access_token"]

        # ユーザー情報を取得
        userinfo_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_access_token}",
                "Accept": "application/json",
            },
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from GitHub",
            )

        userinfo = userinfo_response.json()

        # メールアドレスを取得（プライベートの場合は別エンドポイントから）
        email = userinfo.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {github_access_token}",
                    "Accept": "application/json",
                },
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                primary_email = next(
                    (e["email"] for e in emails if e["primary"] and e["verified"]),
                    None
                )
                email = primary_email or (emails[0]["email"] if emails else None)

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not get email from GitHub",
            )

    # ログイン/登録
    auth_service = AuthService(db)
    device_info = req.headers.get("User-Agent", "unknown")

    user, access_token, refresh_token = await auth_service.oauth_login(
        provider="github",
        oauth_id=str(userinfo["id"]),
        email=email,
        name=userinfo.get("name") or userinfo.get("login"),
        avatar_url=userinfo.get("avatar_url"),
        device_info=device_info,
    )

    # フロントエンドにリダイレクト
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url = f"{frontend_url}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"

    return RedirectResponse(redirect_url)
