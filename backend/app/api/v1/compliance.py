"""セキュリティ・コンプライアンスAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.compliance_service import (
    pii_detector,
    audit_logger,
    data_retention_manager,
    encryption_manager,
    compliance_checker,
    PIIType,
    AuditAction,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tenant_id() -> str:
    return "default-tenant"


# === PII検出 ===

class DetectPIIRequest(BaseModel):
    text: str
    pii_types: Optional[List[str]] = None


@router.post("/pii/detect")
async def detect_pii(
    request: DetectPIIRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テキスト内のPIIを検出"""
    pii_types = None
    if request.pii_types:
        pii_types = [PIIType(pt) for pt in request.pii_types]

    detections = await pii_detector.detect_pii(
        text=request.text,
        pii_types=pii_types,
    )

    return {
        "detections": [
            {
                "type": d.pii_type.value,
                "value": d.value,
                "start": d.start,
                "end": d.end,
                "confidence": d.confidence,
            }
            for d in detections
        ],
        "count": len(detections),
        "has_pii": len(detections) > 0,
    }


class RedactPIIRequest(BaseModel):
    text: str
    pii_types: Optional[List[str]] = None
    replacement_style: str = "mask"  # mask, placeholder, remove


@router.post("/pii/redact")
async def redact_pii(
    request: RedactPIIRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """テキスト内のPIIをマスキング"""
    pii_types = None
    if request.pii_types:
        pii_types = [PIIType(pt) for pt in request.pii_types]

    redacted_text, detections = await pii_detector.redact_text(
        text=request.text,
        pii_types=pii_types,
    )

    return {
        "original_text": request.text,
        "redacted_text": redacted_text,
        "redactions": [
            {
                "type": d.pii_type.value,
                "original": d.value,
                "start": d.start,
                "end": d.end,
            }
            for d in detections
        ],
        "count": len(detections),
    }


@router.get("/pii/types")
async def list_pii_types():
    """サポートされているPIIタイプ一覧"""
    return {
        "types": [
            {"id": PIIType.EMAIL.value, "name": "メールアドレス", "description": "メールアドレスを検出"},
            {"id": PIIType.PHONE.value, "name": "電話番号", "description": "日本の電話番号を検出"},
            {"id": PIIType.CREDIT_CARD.value, "name": "クレジットカード", "description": "クレジットカード番号を検出"},
            {"id": PIIType.SSN.value, "name": "SSN", "description": "社会保障番号を検出"},
            {"id": PIIType.ADDRESS.value, "name": "住所", "description": "日本の住所を検出"},
            {"id": PIIType.NAME.value, "name": "名前", "description": "個人名を検出"},
            {"id": PIIType.DATE_OF_BIRTH.value, "name": "生年月日", "description": "生年月日を検出"},
            {"id": PIIType.IP_ADDRESS.value, "name": "IPアドレス", "description": "IPアドレスを検出"},
            {"id": PIIType.PASSPORT.value, "name": "パスポート", "description": "パスポート番号を検出"},
            {"id": PIIType.DRIVER_LICENSE.value, "name": "運転免許", "description": "運転免許証番号を検出"},
            {"id": PIIType.BANK_ACCOUNT.value, "name": "銀行口座", "description": "銀行口座番号を検出"},
            {"id": PIIType.MY_NUMBER.value, "name": "マイナンバー", "description": "マイナンバーを検出"},
        ]
    }


# === 監査ログ ===

class LogAuditEventRequest(BaseModel):
    action: str
    resource_type: str
    resource_id: str
    details: Optional[dict] = None


@router.post("/audit/log")
async def log_audit_event(
    request: LogAuditEventRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """監査イベントを記録"""
    try:
        action = AuditAction(request.action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    entry = await audit_logger.log(
        tenant_id=tenant_id,
        user_id=str(user_id),
        action=action,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        details=request.details,
    )

    return {
        "id": entry.id,
        "action": entry.action.value,
        "timestamp": entry.timestamp.isoformat(),
        "status": "logged",
    }


@router.get("/audit/logs")
async def get_audit_logs(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """監査ログを取得"""
    action_filter = None
    if action:
        try:
            action_filter = AuditAction(action)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    entries = await audit_logger.get_logs(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action_filter,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "user_id": e.user_id,
                "action": e.action.value,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
                "ip_address": e.ip_address,
            }
            for e in entries
        ],
        "count": len(entries),
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit/actions")
async def list_audit_actions():
    """監査アクション一覧"""
    return {
        "actions": [
            {"id": AuditAction.CREATE.value, "name": "作成"},
            {"id": AuditAction.READ.value, "name": "読み取り"},
            {"id": AuditAction.UPDATE.value, "name": "更新"},
            {"id": AuditAction.DELETE.value, "name": "削除"},
            {"id": AuditAction.EXPORT.value, "name": "エクスポート"},
            {"id": AuditAction.SHARE.value, "name": "共有"},
            {"id": AuditAction.LOGIN.value, "name": "ログイン"},
            {"id": AuditAction.LOGOUT.value, "name": "ログアウト"},
            {"id": AuditAction.PERMISSION_CHANGE.value, "name": "権限変更"},
            {"id": AuditAction.SETTINGS_CHANGE.value, "name": "設定変更"},
        ]
    }


# === データ保持 ===

class SetRetentionPolicyRequest(BaseModel):
    resource_type: str
    retention_days: int
    auto_delete: bool = False
    archive_before_delete: bool = True


@router.post("/retention/policy")
async def set_retention_policy(
    request: SetRetentionPolicyRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データ保持ポリシーを設定"""
    await data_retention_manager.set_policy(
        tenant_id=tenant_id,
        resource_type=request.resource_type,
        retention_days=request.retention_days,
        auto_delete=request.auto_delete,
        archive_before_delete=request.archive_before_delete,
    )

    return {
        "resource_type": request.resource_type,
        "retention_days": request.retention_days,
        "auto_delete": request.auto_delete,
        "archive_before_delete": request.archive_before_delete,
        "status": "policy_set",
    }


@router.get("/retention/policy")
async def get_retention_policies(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データ保持ポリシー一覧"""
    policies = await data_retention_manager.get_policies(tenant_id)

    return {
        "policies": [
            {
                "resource_type": p.resource_type,
                "retention_days": p.retention_days,
                "auto_delete": p.auto_delete,
                "archive_before_delete": p.archive_before_delete,
                "created_at": p.created_at.isoformat(),
            }
            for p in policies
        ],
        "count": len(policies),
    }


@router.get("/retention/expiring")
async def get_expiring_resources(
    days_ahead: int = Query(default=7, le=90),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """期限切れ間近のリソースを取得"""
    resources = await data_retention_manager.get_expiring_resources(
        tenant_id=tenant_id,
        days_ahead=days_ahead,
    )

    return {
        "resources": resources,
        "count": len(resources),
        "days_ahead": days_ahead,
    }


@router.post("/retention/cleanup")
async def run_retention_cleanup(
    dry_run: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """保持期限切れリソースをクリーンアップ"""
    result = await data_retention_manager.cleanup_expired(
        tenant_id=tenant_id,
        dry_run=dry_run,
    )

    return {
        "dry_run": dry_run,
        "archived": result.get("archived", 0),
        "deleted": result.get("deleted", 0),
        "errors": result.get("errors", []),
    }


# === 暗号化 ===

@router.get("/encryption/status")
async def get_encryption_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """暗号化ステータスを取得"""
    status = await encryption_manager.get_status(tenant_id)

    return {
        "at_rest_enabled": status.at_rest_enabled,
        "in_transit_enabled": status.in_transit_enabled,
        "algorithm": status.algorithm,
        "key_rotation_days": status.key_rotation_days,
        "last_key_rotation": status.last_key_rotation.isoformat() if status.last_key_rotation else None,
        "next_key_rotation": status.next_key_rotation.isoformat() if status.next_key_rotation else None,
    }


class UpdateEncryptionRequest(BaseModel):
    at_rest_enabled: Optional[bool] = None
    in_transit_enabled: Optional[bool] = None
    key_rotation_days: Optional[int] = None


@router.put("/encryption/settings")
async def update_encryption_settings(
    request: UpdateEncryptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """暗号化設定を更新"""
    status = await encryption_manager.update_settings(
        tenant_id=tenant_id,
        at_rest_enabled=request.at_rest_enabled,
        in_transit_enabled=request.in_transit_enabled,
        key_rotation_days=request.key_rotation_days,
    )

    return {
        "at_rest_enabled": status.at_rest_enabled,
        "in_transit_enabled": status.in_transit_enabled,
        "key_rotation_days": status.key_rotation_days,
        "status": "updated",
    }


@router.post("/encryption/rotate-key")
async def rotate_encryption_key(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """暗号化キーをローテーション"""
    result = await encryption_manager.rotate_key(tenant_id)

    return {
        "new_key_id": result.get("new_key_id"),
        "old_key_id": result.get("old_key_id"),
        "rotated_at": datetime.utcnow().isoformat(),
        "status": "rotated",
    }


# === コンプライアンスチェック ===

@router.get("/check/gdpr")
async def check_gdpr_compliance(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """GDPRコンプライアンスをチェック"""
    result = await compliance_checker.check_gdpr_compliance(tenant_id)

    return result


@router.get("/check/hipaa")
async def check_hipaa_compliance(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """HIPAAコンプライアンスをチェック"""
    result = await compliance_checker.check_hipaa_compliance(tenant_id)

    return result


class GenerateReportRequest(BaseModel):
    standards: List[str] = ["gdpr", "hipaa"]
    include_recommendations: bool = True


@router.post("/report")
async def generate_compliance_report(
    request: GenerateReportRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """コンプライアンスレポートを生成"""
    report = await compliance_checker.generate_compliance_report(
        tenant_id=tenant_id,
        standards=request.standards,
    )

    return report


@router.get("/standards")
async def list_compliance_standards():
    """サポートされているコンプライアンス基準一覧"""
    return {
        "standards": [
            {
                "id": "gdpr",
                "name": "GDPR",
                "description": "EU一般データ保護規則",
                "region": "EU",
            },
            {
                "id": "hipaa",
                "name": "HIPAA",
                "description": "米国医療保険の相互運用性と説明責任に関する法律",
                "region": "US",
            },
            {
                "id": "pci_dss",
                "name": "PCI DSS",
                "description": "クレジットカード業界データセキュリティ基準",
                "region": "Global",
            },
            {
                "id": "iso27001",
                "name": "ISO 27001",
                "description": "情報セキュリティマネジメントシステム",
                "region": "Global",
            },
            {
                "id": "appi",
                "name": "個人情報保護法",
                "description": "日本の個人情報保護法",
                "region": "JP",
            },
        ]
    }


# === データ主体権利（GDPR） ===

class DataSubjectRequest(BaseModel):
    request_type: str  # access, erasure, portability, rectification
    user_email: str
    reason: Optional[str] = None


@router.post("/dsr")
async def create_data_subject_request(
    request: DataSubjectRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データ主体リクエストを作成"""
    request_id = str(uuid.uuid4())

    # リクエストを記録
    await audit_logger.log(
        tenant_id=tenant_id,
        user_id="system",
        action=AuditAction.CREATE,
        resource_type="data_subject_request",
        resource_id=request_id,
        details={
            "type": request.request_type,
            "email": request.user_email,
            "reason": request.reason,
        },
    )

    return {
        "request_id": request_id,
        "type": request.request_type,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "estimated_completion": "30 days",
    }


@router.get("/dsr/{request_id}")
async def get_data_subject_request(
    request_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データ主体リクエストの状態を取得"""
    # シミュレーション
    return {
        "request_id": request_id,
        "type": "access",
        "status": "processing",
        "created_at": datetime.utcnow().isoformat(),
        "progress": 50,
        "estimated_completion": "15 days remaining",
    }


# === セキュリティ設定 ===

@router.get("/settings")
async def get_security_settings(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """セキュリティ設定を取得"""
    encryption_status = await encryption_manager.get_status(tenant_id)
    policies = await data_retention_manager.get_policies(tenant_id)

    return {
        "encryption": {
            "at_rest_enabled": encryption_status.at_rest_enabled,
            "in_transit_enabled": encryption_status.in_transit_enabled,
        },
        "retention_policies_count": len(policies),
        "pii_detection_enabled": True,
        "audit_logging_enabled": True,
        "mfa_required": False,
        "session_timeout_minutes": 60,
        "password_policy": {
            "min_length": 12,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_numbers": True,
            "require_special": True,
        },
    }


class UpdateSecuritySettingsRequest(BaseModel):
    mfa_required: Optional[bool] = None
    session_timeout_minutes: Optional[int] = None
    pii_detection_enabled: Optional[bool] = None


@router.put("/settings")
async def update_security_settings(
    request: UpdateSecuritySettingsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """セキュリティ設定を更新"""
    # 監査ログに記録
    await audit_logger.log(
        tenant_id=tenant_id,
        user_id="system",
        action=AuditAction.SETTINGS_CHANGE,
        resource_type="security_settings",
        resource_id=tenant_id,
        details=request.dict(exclude_none=True),
    )

    return {
        "status": "updated",
        "changes": request.dict(exclude_none=True),
    }
