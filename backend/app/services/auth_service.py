"""認証サービス"""

import os
import uuid
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
import bcrypt
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, RefreshToken

# JWT設定
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30


class AuthService:
    """認証サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================
    # パスワード関連
    # ==================

    @staticmethod
    def hash_password(password: str) -> str:
        """パスワードをハッシュ化"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """パスワードを検証"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    # ==================
    # トークン関連
    # ==================

    @staticmethod
    def create_access_token(
        user_id: uuid.UUID,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """アクセストークンを作成"""
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        payload = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token() -> Tuple[str, str]:
        """リフレッシュトークンを作成（トークン, ハッシュ）"""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash

    @staticmethod
    def decode_access_token(token: str) -> Optional[dict]:
        """アクセストークンをデコード"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    # ==================
    # ユーザー登録・ログイン
    # ==================

    async def register(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> User:
        """ユーザー登録"""
        # メールアドレスの重複チェック
        existing = await self.db.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")

        # ユーザー作成
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=self.hash_password(password),
            name=name,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def login(
        self,
        email: str,
        password: str,
        device_info: Optional[str] = None,
    ) -> Optional[Tuple[User, str, str]]:
        """ログイン（ユーザー, アクセストークン, リフレッシュトークン）"""
        # ユーザーを検索
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            logging.warning(f"Login failed for email: {email}. User not found.")
            return None

        if not user.hashed_password:
            # OAuthユーザーはパスワードログイン不可
            logging.warning(f"Login failed for email: {email}. User is an OAuth user and has no password.")
            return None

        if not self.verify_password(password, user.hashed_password):
            logging.warning(f"Login failed for email: {email}. Invalid password.")
            return None

        if not user.is_active:
            logging.warning(f"Login failed for email: {email}. User is not active.")
            return None

        # トークン生成
        access_token = self.create_access_token(user.id)
        refresh_token, refresh_hash = self.create_refresh_token()

        # リフレッシュトークンを保存
        token_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            device_info=device_info,
            expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(token_record)
        await self.db.commit()

        return user, access_token, refresh_token

    async def logout(self, user_id: uuid.UUID, refresh_token: str) -> bool:
        """ログアウト（リフレッシュトークンを無効化）"""
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at == None,
            )
        )
        token_record = result.scalar_one_or_none()

        if token_record:
            token_record.revoked_at = datetime.utcnow()
            await self.db.commit()
            return True

        return False

    async def logout_all(self, user_id: uuid.UUID) -> int:
        """全デバイスからログアウト"""
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at == None,
            )
        )
        tokens = result.scalars().all()

        count = 0
        for token in tokens:
            token.revoked_at = datetime.utcnow()
            count += 1

        await self.db.commit()
        return count

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> Optional[Tuple[str, str]]:
        """アクセストークンをリフレッシュ（新しいアクセストークン, 新しいリフレッシュトークン）"""
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at == None,
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            return None

        if token_record.expires_at < datetime.utcnow():
            # 期限切れ
            token_record.revoked_at = datetime.utcnow()
            await self.db.commit()
            return None

        # 古いトークンを無効化
        token_record.revoked_at = datetime.utcnow()

        # 新しいトークンを生成
        new_access_token = self.create_access_token(token_record.user_id)
        new_refresh_token, new_refresh_hash = self.create_refresh_token()

        # 新しいリフレッシュトークンを保存
        new_token_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=token_record.user_id,
            token_hash=new_refresh_hash,
            device_info=token_record.device_info,
            expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(new_token_record)
        await self.db.commit()

        return new_access_token, new_refresh_token

    # ==================
    # ユーザー取得
    # ==================

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """IDでユーザーを取得"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """メールアドレスでユーザーを取得"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    # ==================
    # OAuth
    # ==================

    async def oauth_login(
        self,
        provider: str,
        oauth_id: str,
        email: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        device_info: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """OAuthログイン/登録"""
        # 既存ユーザーを検索
        result = await self.db.execute(
            select(User).where(
                User.oauth_provider == provider,
                User.oauth_id == oauth_id,
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            # メールアドレスで検索
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if user:
                # 既存ユーザーにOAuth情報を追加
                user.oauth_provider = provider
                user.oauth_id = oauth_id
                if name and not user.name:
                    user.name = name
                if avatar_url:
                    user.avatar_url = avatar_url
            else:
                # 新規ユーザー作成
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    name=name,
                    avatar_url=avatar_url,
                    oauth_provider=provider,
                    oauth_id=oauth_id,
                    is_active=True,
                    is_verified=True,  # OAuthは検証済み
                )
                self.db.add(user)

        # トークン生成
        access_token = self.create_access_token(user.id)
        refresh_token, refresh_hash = self.create_refresh_token()

        # リフレッシュトークンを保存
        token_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            device_info=device_info,
            expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(token_record)
        await self.db.commit()
        await self.db.refresh(user)

        return user, access_token, refresh_token

    # ==================
    # パスワード変更
    # ==================

    async def change_password(
        self,
        user_id: uuid.UUID,
        old_password: str,
        new_password: str,
    ) -> bool:
        """パスワード変更"""
        user = await self.get_user_by_id(user_id)

        if not user or not user.hashed_password:
            return False

        if not self.verify_password(old_password, user.hashed_password):
            return False

        user.hashed_password = self.hash_password(new_password)
        await self.db.commit()

        # 全デバイスからログアウト
        await self.logout_all(user_id)

        return True

    async def reset_password(
        self,
        email: str,
        new_password: str,
    ) -> bool:
        """パスワードリセット（トークン検証は別途必要）"""
        user = await self.get_user_by_email(email)

        if not user:
            return False

        user.hashed_password = self.hash_password(new_password)
        await self.db.commit()

        # 全デバイスからログアウト
        await self.logout_all(user.id)

        return True
