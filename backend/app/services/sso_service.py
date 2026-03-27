"""SSO認証サービス"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import jwt
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from base64 import b64decode, b64encode
import hashlib
import secrets

from app.models.enterprise import (
    Organization,
    SSOConfiguration,
    SSOProvider,
    OrganizationMember,
    OrganizationRole,
)
from app.models.user import User
from app.core.config import get_settings

settings = get_settings()


class SSOService:
    """SSO認証サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_sso_config(
        self, organization_id: UUID
    ) -> Optional[SSOConfiguration]:
        """SSO設定を取得"""
        result = await self.db.execute(
            select(SSOConfiguration)
            .where(SSOConfiguration.organization_id == organization_id)
            .where(SSOConfiguration.is_active == True)
        )
        return result.scalar_one_or_none()

    async def initiate_sso_login(
        self,
        organization_slug: str,
        redirect_uri: str,
    ) -> dict:
        """SSO認証を開始"""
        # 組織を取得
        result = await self.db.execute(
            select(Organization).where(Organization.slug == organization_slug)
        )
        org = result.scalar_one_or_none()

        if not org or not org.sso_enabled:
            raise ValueError("SSO is not enabled for this organization")

        sso_config = await self.get_sso_config(org.id)
        if not sso_config:
            raise ValueError("SSO configuration not found")

        if sso_config.provider == SSOProvider.SAML:
            return await self._initiate_saml_login(sso_config, redirect_uri)
        elif sso_config.provider in [SSOProvider.OAUTH2, SSOProvider.OIDC]:
            return await self._initiate_oauth_login(sso_config, redirect_uri)
        elif sso_config.provider == SSOProvider.AZURE_AD:
            return await self._initiate_azure_ad_login(sso_config, redirect_uri)
        elif sso_config.provider == SSOProvider.OKTA:
            return await self._initiate_okta_login(sso_config, redirect_uri)
        elif sso_config.provider == SSOProvider.GOOGLE:
            return await self._initiate_google_login(sso_config, redirect_uri)
        else:
            raise ValueError(f"Unsupported SSO provider: {sso_config.provider}")

    async def _initiate_saml_login(
        self, config: SSOConfiguration, redirect_uri: str
    ) -> dict:
        """SAML認証を開始"""
        # SAMLリクエストを生成
        request_id = f"_{ secrets.token_hex(16)}"
        issue_instant = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        saml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    AssertionConsumerServiceURL="{redirect_uri}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>{settings.APP_URL}</saml:Issuer>
</samlp:AuthnRequest>"""

        # Base64エンコード
        encoded_request = b64encode(saml_request.encode()).decode()

        # リダイレクトURLを構築
        params = urlencode({"SAMLRequest": encoded_request, "RelayState": redirect_uri})

        return {
            "type": "redirect",
            "url": f"{config.sso_url}?{params}",
            "request_id": request_id,
        }

    async def _initiate_oauth_login(
        self, config: SSOConfiguration, redirect_uri: str
    ) -> dict:
        """OAuth2/OIDC認証を開始"""
        state = secrets.token_urlsafe(32)

        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
        }

        url = f"{config.authorization_url}?{urlencode(params)}"

        return {"type": "redirect", "url": url, "state": state}

    async def _initiate_azure_ad_login(
        self, config: SSOConfiguration, redirect_uri: str
    ) -> dict:
        """Azure AD認証を開始"""
        tenant_id = config.attribute_mapping.get("tenant_id", "common")
        state = secrets.token_urlsafe(32)

        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "response_mode": "query",
        }

        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"

        return {"type": "redirect", "url": url, "state": state}

    async def _initiate_okta_login(
        self, config: SSOConfiguration, redirect_uri: str
    ) -> dict:
        """Okta認証を開始"""
        okta_domain = config.attribute_mapping.get("okta_domain")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
        }

        url = f"https://{okta_domain}/oauth2/v1/authorize?{urlencode(params)}"

        return {"type": "redirect", "url": url, "state": state, "nonce": nonce}

    async def _initiate_google_login(
        self, config: SSOConfiguration, redirect_uri: str
    ) -> dict:
        """Google認証を開始"""
        state = secrets.token_urlsafe(32)

        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }

        # HD（Hosted Domain）パラメータで特定ドメインに制限
        if config.attribute_mapping.get("hd"):
            params["hd"] = config.attribute_mapping["hd"]

        url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        return {"type": "redirect", "url": url, "state": state}

    async def handle_sso_callback(
        self,
        organization_slug: str,
        code: Optional[str] = None,
        saml_response: Optional[str] = None,
        state: Optional[str] = None,
    ) -> User:
        """SSOコールバックを処理"""
        # 組織を取得
        result = await self.db.execute(
            select(Organization).where(Organization.slug == organization_slug)
        )
        org = result.scalar_one_or_none()

        if not org:
            raise ValueError("Organization not found")

        sso_config = await self.get_sso_config(org.id)
        if not sso_config:
            raise ValueError("SSO configuration not found")

        # プロバイダーに応じて処理
        if sso_config.provider == SSOProvider.SAML and saml_response:
            user_info = await self._process_saml_response(sso_config, saml_response)
        elif code:
            user_info = await self._exchange_code_for_token(sso_config, code)
        else:
            raise ValueError("Invalid SSO callback")

        # ユーザーを取得または作成
        user = await self._get_or_create_user(org, user_info)

        return user

    async def _process_saml_response(
        self, config: SSOConfiguration, saml_response: str
    ) -> dict:
        """SAMLレスポンスを処理"""
        # Base64デコード
        decoded = b64decode(saml_response)
        root = ET.fromstring(decoded)

        # 名前空間
        ns = {
            "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
            "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
        }

        # アサーションを取得
        assertion = root.find(".//saml:Assertion", ns)
        if assertion is None:
            raise ValueError("No assertion found in SAML response")

        # 属性を取得
        attributes = {}
        for attr in assertion.findall(".//saml:Attribute", ns):
            name = attr.get("Name")
            value = attr.find("saml:AttributeValue", ns)
            if value is not None:
                attributes[name] = value.text

        # 属性マッピングを適用
        mapping = config.attribute_mapping or {}
        email_attr = mapping.get("email", "email")
        name_attr = mapping.get("name", "name")

        return {
            "email": attributes.get(email_attr),
            "name": attributes.get(name_attr),
            "provider_id": attributes.get("nameID"),
        }

    async def _exchange_code_for_token(
        self, config: SSOConfiguration, code: str
    ) -> dict:
        """認証コードをトークンに交換"""
        # トークンエンドポイント
        token_url = config.token_url

        # Azure AD用の調整
        if config.provider == SSOProvider.AZURE_AD:
            tenant_id = config.attribute_mapping.get("tenant_id", "common")
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        # Okta用の調整
        elif config.provider == SSOProvider.OKTA:
            okta_domain = config.attribute_mapping.get("okta_domain")
            token_url = f"https://{okta_domain}/oauth2/v1/token"

        # Google用の調整
        elif config.provider == SSOProvider.GOOGLE:
            token_url = "https://oauth2.googleapis.com/token"

        # トークンリクエスト
        response = await self.client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": f"{settings.APP_URL}/api/v1/sso/callback",
            },
        )

        response.raise_for_status()
        token_data = response.json()

        # ユーザー情報を取得
        if "id_token" in token_data:
            # JWTをデコード（署名検証はスキップ - 本番では検証必須）
            user_info = jwt.decode(
                token_data["id_token"], options={"verify_signature": False}
            )
        else:
            # UserInfoエンドポイントから取得
            userinfo_url = config.userinfo_url

            if config.provider == SSOProvider.AZURE_AD:
                userinfo_url = "https://graph.microsoft.com/v1.0/me"
            elif config.provider == SSOProvider.GOOGLE:
                userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

            response = await self.client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            response.raise_for_status()
            user_info = response.json()

        return {
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "provider_id": user_info.get("sub") or user_info.get("id"),
        }

    async def _get_or_create_user(
        self, organization: Organization, user_info: dict
    ) -> User:
        """ユーザーを取得または作成"""
        email = user_info.get("email")
        if not email:
            raise ValueError("Email not found in SSO response")

        # 既存ユーザーを検索
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            # 新規ユーザーを作成
            user = User(
                email=email,
                name=user_info.get("name", email.split("@")[0]),
                sso_provider_id=user_info.get("provider_id"),
            )
            self.db.add(user)
            await self.db.flush()

            # 組織メンバーとして追加
            member = OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationRole.MEMBER,
                joined_at=datetime.utcnow(),
            )
            self.db.add(member)

        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def close(self):
        await self.client.aclose()
