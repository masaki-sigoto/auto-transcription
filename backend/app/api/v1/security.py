"""セキュリティ・コンプライアンスAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.security_service import (
    EncryptionService,
    DataRetentionService,
    AccessControlService,
    SecurityAlertService,
    GDPRService,
    RetentionPolicy,
)

router = APIRouter(prefix="/security", tags=["security"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# === 暗号化 ===

class EncryptRequest(BaseModel):
    data: str
    context: Optional[str] = None


class EncryptResponse(BaseModel):
    ciphertext: str
    salt: str
    algorithm: str


class DecryptRequest(BaseModel):
    ciphertext: str
    salt: str


@router.post("/encrypt", response_model=EncryptResponse)
async def encrypt_data(
    request: EncryptRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """データを暗号化"""
    service = EncryptionService()
    result = service.encrypt(request.data, request.context)

    return EncryptResponse(
        ciphertext=result["ciphertext"],
        salt=result["salt"],
        algorithm=result["algorithm"],
    )


@router.post("/decrypt")
async def decrypt_data(
    request: DecryptRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """データを復号"""
    service = EncryptionService()

    try:
        decrypted = service.decrypt({
            "ciphertext": request.ciphertext,
            "salt": request.salt,
        })
        return {"data": decrypted}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Decryption failed")


# === データ保持ポリシー ===

class RetentionPolicyRequest(BaseModel):
    name: str
    retention_days: int
    data_types: List[str]
    auto_delete: bool = True
    archive_before_delete: bool = True
    compliance_frameworks: Optional[List[str]] = None
    description: Optional[str] = None


class RetentionPolicyResponse(BaseModel):
    policy_id: str
    name: str
    description: str
    retention_days: int
    data_types: List[str]
    auto_delete: bool
    archive_before_delete: bool
    compliance_frameworks: List[str]


@router.post("/retention-policies", response_model=RetentionPolicyResponse)
async def create_retention_policy(
    request: RetentionPolicyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """保持ポリシーを作成"""
    service = DataRetentionService(db)

    policy = await service.create_policy(
        name=request.name,
        retention_days=request.retention_days,
        data_types=request.data_types,
        auto_delete=request.auto_delete,
        archive_before_delete=request.archive_before_delete,
        compliance_frameworks=request.compliance_frameworks,
        description=request.description,
    )

    return RetentionPolicyResponse(
        policy_id=policy.policy_id,
        name=policy.name,
        description=policy.description,
        retention_days=policy.retention_days,
        data_types=policy.data_types,
        auto_delete=policy.auto_delete,
        archive_before_delete=policy.archive_before_delete,
        compliance_frameworks=policy.compliance_frameworks,
    )


@router.get("/retention-policies", response_model=List[RetentionPolicyResponse])
async def get_retention_policies(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """保持ポリシー一覧を取得"""
    service = DataRetentionService(db)
    policies = await service.get_policies()

    return [
        RetentionPolicyResponse(
            policy_id=p.policy_id,
            name=p.name,
            description=p.description,
            retention_days=p.retention_days,
            data_types=p.data_types,
            auto_delete=p.auto_delete,
            archive_before_delete=p.archive_before_delete,
            compliance_frameworks=p.compliance_frameworks,
        )
        for p in policies
    ]


@router.post("/retention-policies/apply")
async def apply_retention_policies(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """保持ポリシーを適用"""
    service = DataRetentionService(db)
    result = await service.apply_retention_policies()

    return {"status": "applied", "deleted_counts": result}


# === アクセスログ ===

class AccessLogResponse(BaseModel):
    id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    ip_address: str
    timestamp: str
    success: bool


@router.get("/access-logs", response_model=List[AccessLogResponse])
async def get_access_logs(
    user_id_filter: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アクセスログを取得"""
    service = AccessControlService(db)

    user_uuid = None
    if user_id_filter:
        try:
            user_uuid = uuid.UUID(user_id_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")

    logs = await service.get_access_logs(
        user_id=user_uuid,
        resource_type=resource_type,
        action=action,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    return [
        AccessLogResponse(
            id=log.id,
            user_id=log.user_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            timestamp=log.timestamp,
            success=log.success,
        )
        for log in logs
    ]


# === セキュリティアラート ===

class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    description: str
    user_id: Optional[str]
    timestamp: str
    resolved: bool


@router.get("/alerts", response_model=List[AlertResponse])
async def get_security_alerts(
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """セキュリティアラートを取得"""
    service = SecurityAlertService(db)

    alerts = await service.get_alerts(
        severity=severity,
        resolved=resolved,
        limit=limit,
    )

    return [
        AlertResponse(
            id=a.id,
            alert_type=a.alert_type,
            severity=a.severity,
            title=a.title,
            description=a.description,
            user_id=a.user_id,
            timestamp=a.timestamp,
            resolved=a.resolved,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """アラートを解決済みにする"""
    from sqlalchemy import text

    await db.execute(
        text("""
            UPDATE security_alerts
            SET resolved = true, resolved_at = :now
            WHERE id = :id
        """),
        {"id": alert_id, "now": datetime.utcnow().isoformat()},
    )
    await db.commit()

    return {"status": "resolved", "alert_id": alert_id}


# === GDPR ===

@router.get("/gdpr/export")
async def export_user_data(
    target_user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ユーザーデータをエクスポート（GDPR データポータビリティ）"""
    service = GDPRService(db)

    target = user_id
    if target_user_id:
        try:
            target = uuid.UUID(target_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")

    data = await service.export_user_data(target)

    return data


@router.delete("/gdpr/delete")
async def delete_user_data(
    target_user_id: str,
    retain_anonymized: bool = False,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """ユーザーデータを削除（GDPR 忘れられる権利）"""
    try:
        target = uuid.UUID(target_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    service = GDPRService(db)
    result = await service.delete_user_data(target, retain_anonymized)

    return {"status": "deleted", "deleted_counts": result}


class ConsentRequest(BaseModel):
    consent_type: str
    granted: bool


@router.post("/gdpr/consent")
async def record_consent(
    request: ConsentRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """同意を記録"""
    service = GDPRService(db)

    ip_address = req.client.host if req.client else "unknown"

    consent_id = await service.record_consent(
        user_id=user_id,
        consent_type=request.consent_type,
        granted=request.granted,
        ip_address=ip_address,
    )

    return {"status": "recorded", "consent_id": consent_id}


# === 権限チェック ===

@router.get("/check-permission")
async def check_permission(
    resource_type: str,
    resource_id: str,
    action: str,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """権限をチェック"""
    try:
        resource_uuid = uuid.UUID(resource_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid resource_id format")

    service = AccessControlService(db)
    has_permission = await service.check_permission(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_uuid,
        action=action,
    )

    return {"has_permission": has_permission}
