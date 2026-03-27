"""CRM連携サービス"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID
import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()


class CRMContact(BaseModel):
    """CRM連絡先"""
    id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    company: Optional[str]
    title: Optional[str]
    provider: str  # salesforce, hubspot


class CRMDeal(BaseModel):
    """CRM商談"""
    id: str
    name: str
    amount: Optional[float]
    stage: str
    close_date: Optional[datetime]
    contact_id: Optional[str]
    provider: str


class CRMActivity(BaseModel):
    """CRMアクティビティ"""
    id: str
    type: str  # call, meeting, email, note
    subject: str
    description: Optional[str]
    date: datetime
    contact_id: Optional[str]
    deal_id: Optional[str]


class SalesforceService:
    """Salesforce連携サービス"""

    def __init__(self, access_token: str, instance_url: str):
        self.access_token = access_token
        self.instance_url = instance_url
        self.client = httpx.AsyncClient(
            base_url=f"{instance_url}/services/data/v58.0",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get_contacts(
        self,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> List[CRMContact]:
        """連絡先一覧を取得"""
        query = "SELECT Id, Name, Email, Phone, Account.Name, Title FROM Contact"
        if search:
            query += f" WHERE Name LIKE '%{search}%' OR Email LIKE '%{search}%'"
        query += f" LIMIT {limit}"

        response = await self.client.get("/query", params={"q": query})
        response.raise_for_status()
        data = response.json()

        contacts = []
        for record in data.get("records", []):
            contacts.append(
                CRMContact(
                    id=record["Id"],
                    name=record["Name"],
                    email=record.get("Email"),
                    phone=record.get("Phone"),
                    company=record.get("Account", {}).get("Name") if record.get("Account") else None,
                    title=record.get("Title"),
                    provider="salesforce",
                )
            )

        return contacts

    async def get_deals(
        self,
        contact_id: Optional[str] = None,
        stage: Optional[str] = None,
        limit: int = 50,
    ) -> List[CRMDeal]:
        """商談一覧を取得"""
        query = "SELECT Id, Name, Amount, StageName, CloseDate, ContactId FROM Opportunity"
        conditions = []
        if contact_id:
            conditions.append(f"ContactId = '{contact_id}'")
        if stage:
            conditions.append(f"StageName = '{stage}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" LIMIT {limit}"

        response = await self.client.get("/query", params={"q": query})
        response.raise_for_status()
        data = response.json()

        deals = []
        for record in data.get("records", []):
            deals.append(
                CRMDeal(
                    id=record["Id"],
                    name=record["Name"],
                    amount=record.get("Amount"),
                    stage=record["StageName"],
                    close_date=datetime.fromisoformat(record["CloseDate"]) if record.get("CloseDate") else None,
                    contact_id=record.get("ContactId"),
                    provider="salesforce",
                )
            )

        return deals

    async def create_activity(
        self,
        subject: str,
        description: str,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        activity_type: str = "Task",
    ) -> CRMActivity:
        """アクティビティを作成"""
        payload = {
            "Subject": subject,
            "Description": description,
            "Status": "Completed",
            "Priority": "Normal",
            "ActivityDate": datetime.utcnow().strftime("%Y-%m-%d"),
        }

        if contact_id:
            payload["WhoId"] = contact_id
        if deal_id:
            payload["WhatId"] = deal_id

        response = await self.client.post(f"/sobjects/{activity_type}", json=payload)
        response.raise_for_status()
        data = response.json()

        return CRMActivity(
            id=data["id"],
            type=activity_type.lower(),
            subject=subject,
            description=description,
            date=datetime.utcnow(),
            contact_id=contact_id,
            deal_id=deal_id,
        )

    async def log_transcription(
        self,
        transcription_id: str,
        title: str,
        summary: str,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> CRMActivity:
        """文字起こしをCRMに記録"""
        description = f"""
会議記録: {title}

概要:
{summary}

文字起こしID: {transcription_id}
"""
        return await self.create_activity(
            subject=f"会議記録: {title}",
            description=description,
            contact_id=contact_id,
            deal_id=deal_id,
            activity_type="Task",
        )

    async def close(self):
        await self.client.aclose()


class HubSpotService:
    """HubSpot連携サービス"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url="https://api.hubapi.com",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get_contacts(
        self,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> List[CRMContact]:
        """連絡先一覧を取得"""
        params = {
            "limit": limit,
            "properties": "firstname,lastname,email,phone,company,jobtitle",
        }

        if search:
            # 検索APIを使用
            response = await self.client.post(
                "/crm/v3/objects/contacts/search",
                json={
                    "filterGroups": [
                        {
                            "filters": [
                                {
                                    "propertyName": "email",
                                    "operator": "CONTAINS_TOKEN",
                                    "value": search,
                                }
                            ]
                        }
                    ],
                    "limit": limit,
                    "properties": ["firstname", "lastname", "email", "phone", "company", "jobtitle"],
                },
            )
        else:
            response = await self.client.get("/crm/v3/objects/contacts", params=params)

        response.raise_for_status()
        data = response.json()

        contacts = []
        for record in data.get("results", []):
            props = record.get("properties", {})
            name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            contacts.append(
                CRMContact(
                    id=record["id"],
                    name=name or "Unknown",
                    email=props.get("email"),
                    phone=props.get("phone"),
                    company=props.get("company"),
                    title=props.get("jobtitle"),
                    provider="hubspot",
                )
            )

        return contacts

    async def get_deals(
        self,
        contact_id: Optional[str] = None,
        stage: Optional[str] = None,
        limit: int = 50,
    ) -> List[CRMDeal]:
        """商談一覧を取得"""
        params = {
            "limit": limit,
            "properties": "dealname,amount,dealstage,closedate",
        }

        response = await self.client.get("/crm/v3/objects/deals", params=params)
        response.raise_for_status()
        data = response.json()

        deals = []
        for record in data.get("results", []):
            props = record.get("properties", {})

            # ステージでフィルタ
            if stage and props.get("dealstage") != stage:
                continue

            deals.append(
                CRMDeal(
                    id=record["id"],
                    name=props.get("dealname", "Unknown"),
                    amount=float(props["amount"]) if props.get("amount") else None,
                    stage=props.get("dealstage", "unknown"),
                    close_date=datetime.fromisoformat(props["closedate"]) if props.get("closedate") else None,
                    contact_id=None,  # 関連付けは別途取得が必要
                    provider="hubspot",
                )
            )

        return deals

    async def create_note(
        self,
        content: str,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> CRMActivity:
        """ノートを作成"""
        payload = {
            "properties": {
                "hs_note_body": content,
                "hs_timestamp": datetime.utcnow().isoformat() + "Z",
            },
        }

        response = await self.client.post("/crm/v3/objects/notes", json=payload)
        response.raise_for_status()
        data = response.json()

        note_id = data["id"]

        # 連絡先に関連付け
        if contact_id:
            await self.client.put(
                f"/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact"
            )

        # 商談に関連付け
        if deal_id:
            await self.client.put(
                f"/crm/v3/objects/notes/{note_id}/associations/deals/{deal_id}/note_to_deal"
            )

        return CRMActivity(
            id=note_id,
            type="note",
            subject="Note",
            description=content,
            date=datetime.utcnow(),
            contact_id=contact_id,
            deal_id=deal_id,
        )

    async def log_transcription(
        self,
        transcription_id: str,
        title: str,
        summary: str,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> CRMActivity:
        """文字起こしをCRMに記録"""
        content = f"""
<h3>会議記録: {title}</h3>
<p><strong>概要:</strong></p>
<p>{summary}</p>
<p><em>文字起こしID: {transcription_id}</em></p>
"""
        return await self.create_note(
            content=content,
            contact_id=contact_id,
            deal_id=deal_id,
        )

    async def close(self):
        await self.client.aclose()


class CRMIntegrationService:
    """CRM統合サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_service(
        self,
        provider: str,
        access_token: str,
        instance_url: Optional[str] = None,
    ):
        """プロバイダーに応じたサービスを取得"""
        if provider == "salesforce":
            if not instance_url:
                raise ValueError("Salesforce requires instance_url")
            return SalesforceService(access_token, instance_url)
        elif provider == "hubspot":
            return HubSpotService(access_token)
        else:
            raise ValueError(f"Unsupported CRM provider: {provider}")

    async def sync_contacts_to_crm(
        self,
        provider: str,
        access_token: str,
        transcription_id: UUID,
        participants: List[str],
        instance_url: Optional[str] = None,
    ) -> List[CRMContact]:
        """参加者をCRM連絡先と紐付け"""
        service = self.get_service(provider, access_token, instance_url)

        matched_contacts = []
        try:
            for participant in participants:
                # メールアドレスで検索
                contacts = await service.get_contacts(search=participant, limit=1)
                if contacts:
                    matched_contacts.append(contacts[0])
        finally:
            await service.close()

        return matched_contacts

    async def export_to_crm(
        self,
        provider: str,
        access_token: str,
        transcription_id: str,
        title: str,
        summary: str,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        instance_url: Optional[str] = None,
    ) -> CRMActivity:
        """文字起こしをCRMにエクスポート"""
        service = self.get_service(provider, access_token, instance_url)

        try:
            return await service.log_transcription(
                transcription_id=transcription_id,
                title=title,
                summary=summary,
                contact_id=contact_id,
                deal_id=deal_id,
            )
        finally:
            await service.close()
