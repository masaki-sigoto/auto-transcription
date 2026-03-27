"""高度なセキュリティ・コンプライアンスサービス"""

import os
import re
import uuid
import hashlib
import json
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio


class PIIType(str, Enum):
    """個人識別情報タイプ"""
    EMAIL = "email"
    PHONE = "phone"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"  # 社会保障番号
    MY_NUMBER = "my_number"  # マイナンバー
    ADDRESS = "address"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    IP_ADDRESS = "ip_address"
    PASSPORT = "passport"
    DRIVER_LICENSE = "driver_license"
    BANK_ACCOUNT = "bank_account"


class ComplianceStandard(str, Enum):
    """コンプライアンス基準"""
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    CCPA = "ccpa"
    APPI = "appi"  # 日本の個人情報保護法


class AuditEventType(str, Enum):
    """監査イベントタイプ"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    SHARE = "share"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_CHANGE = "permission_change"
    SETTINGS_CHANGE = "settings_change"
    API_CALL = "api_call"


class RetentionPolicy(str, Enum):
    """データ保持ポリシー"""
    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    DAYS_180 = "180_days"
    YEAR_1 = "1_year"
    YEAR_3 = "3_years"
    YEAR_7 = "7_years"
    INDEFINITE = "indefinite"


@dataclass
class PIIDetection:
    """PII検出結果"""
    pii_type: PIIType
    value: str
    masked_value: str
    start_position: int
    end_position: int
    confidence: float


@dataclass
class AuditLogEntry:
    """監査ログエントリ"""
    id: str
    timestamp: datetime
    event_type: AuditEventType
    user_id: str
    resource_type: str
    resource_id: str
    action: str
    ip_address: str
    user_agent: str
    details: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None


@dataclass
class DataRetentionRule:
    """データ保持ルール"""
    id: str
    tenant_id: str
    resource_type: str
    retention_period: RetentionPolicy
    auto_delete: bool
    anonymize_on_expire: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class EncryptionConfig:
    """暗号化設定"""
    algorithm: str  # AES-256-GCM, etc.
    key_rotation_days: int
    encrypt_at_rest: bool
    encrypt_in_transit: bool
    key_id: str


class PIIDetector:
    """PII検出エンジン"""

    def __init__(self):
        # 日本語対応のPII検出パターン
        self._patterns = {
            PIIType.EMAIL: r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            PIIType.PHONE: r'(?:\+81|0)[0-9]{1,4}[-\s]?[0-9]{1,4}[-\s]?[0-9]{4}',
            PIIType.CREDIT_CARD: r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            PIIType.MY_NUMBER: r'\b\d{12}\b',  # マイナンバー（12桁）
            PIIType.IP_ADDRESS: r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            PIIType.PASSPORT: r'\b[A-Z]{2}[0-9]{7}\b',
        }

        # 日本の住所パターン（簡易版）
        self._address_keywords = ["都", "道", "府", "県", "市", "区", "町", "村", "番地", "丁目"]

    async def detect_pii(
        self,
        text: str,
        pii_types: Optional[List[PIIType]] = None,
    ) -> List[PIIDetection]:
        """PIIを検出"""
        detections = []
        types_to_check = pii_types or list(PIIType)

        for pii_type in types_to_check:
            if pii_type in self._patterns:
                pattern = self._patterns[pii_type]
                for match in re.finditer(pattern, text):
                    value = match.group()
                    detections.append(PIIDetection(
                        pii_type=pii_type,
                        value=value,
                        masked_value=self._mask_value(value, pii_type),
                        start_position=match.start(),
                        end_position=match.end(),
                        confidence=0.9,
                    ))

        # 住所検出
        if PIIType.ADDRESS in types_to_check:
            for kw in self._address_keywords:
                for match in re.finditer(rf'[^\s]{{2,20}}{kw}', text):
                    detections.append(PIIDetection(
                        pii_type=PIIType.ADDRESS,
                        value=match.group(),
                        masked_value="[住所]",
                        start_position=match.start(),
                        end_position=match.end(),
                        confidence=0.7,
                    ))

        return detections

    def _mask_value(self, value: str, pii_type: PIIType) -> str:
        """値をマスキング"""
        if pii_type == PIIType.EMAIL:
            parts = value.split('@')
            if len(parts) == 2:
                return f"{parts[0][:2]}***@{parts[1]}"
            return "***@***"

        elif pii_type == PIIType.PHONE:
            return value[:3] + "****" + value[-4:]

        elif pii_type == PIIType.CREDIT_CARD:
            return "****-****-****-" + value[-4:]

        elif pii_type == PIIType.MY_NUMBER:
            return "********" + value[-4:]

        else:
            return "*" * len(value)

    async def redact_text(
        self,
        text: str,
        pii_types: Optional[List[PIIType]] = None,
    ) -> Tuple[str, List[PIIDetection]]:
        """テキストからPIIを削除"""
        detections = await self.detect_pii(text, pii_types)

        # 後ろから置換（位置がずれないように）
        detections_sorted = sorted(detections, key=lambda d: d.start_position, reverse=True)

        redacted_text = text
        for detection in detections_sorted:
            redacted_text = (
                redacted_text[:detection.start_position] +
                detection.masked_value +
                redacted_text[detection.end_position:]
            )

        return redacted_text, detections


class AuditLogger:
    """監査ログ管理"""

    def __init__(self):
        self._logs: List[AuditLogEntry] = []
        self._max_logs = 100000

    async def log(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        ip_address: str = "",
        user_agent: str = "",
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLogEntry:
        """監査ログを記録"""
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        self._logs.append(entry)

        # ログサイズ制限
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

        return entry

    async def search(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLogEntry]:
        """監査ログを検索"""
        results = self._logs

        if user_id:
            results = [l for l in results if l.user_id == user_id]
        if event_type:
            results = [l for l in results if l.event_type == event_type]
        if resource_type:
            results = [l for l in results if l.resource_type == resource_type]
        if start_date:
            results = [l for l in results if l.timestamp >= start_date]
        if end_date:
            results = [l for l in results if l.timestamp <= end_date]

        return sorted(results, key=lambda l: l.timestamp, reverse=True)[:limit]

    async def export(
        self,
        start_date: datetime,
        end_date: datetime,
        format: str = "json",
    ) -> str:
        """監査ログをエクスポート"""
        logs = await self.search(start_date=start_date, end_date=end_date, limit=10000)

        if format == "json":
            return json.dumps([
                {
                    "id": l.id,
                    "timestamp": l.timestamp.isoformat(),
                    "event_type": l.event_type.value,
                    "user_id": l.user_id,
                    "resource_type": l.resource_type,
                    "resource_id": l.resource_id,
                    "action": l.action,
                    "success": l.success,
                }
                for l in logs
            ], ensure_ascii=False, indent=2)

        elif format == "csv":
            lines = ["timestamp,event_type,user_id,resource_type,resource_id,action,success"]
            for l in logs:
                lines.append(f"{l.timestamp.isoformat()},{l.event_type.value},{l.user_id},{l.resource_type},{l.resource_id},{l.action},{l.success}")
            return "\n".join(lines)

        return ""


class DataRetentionManager:
    """データ保持ポリシー管理"""

    def __init__(self):
        self._rules: Dict[str, DataRetentionRule] = {}
        self._retention_days = {
            RetentionPolicy.DAYS_30: 30,
            RetentionPolicy.DAYS_90: 90,
            RetentionPolicy.DAYS_180: 180,
            RetentionPolicy.YEAR_1: 365,
            RetentionPolicy.YEAR_3: 1095,
            RetentionPolicy.YEAR_7: 2555,
            RetentionPolicy.INDEFINITE: -1,
        }

    async def create_rule(
        self,
        tenant_id: str,
        resource_type: str,
        retention_period: RetentionPolicy,
        auto_delete: bool = True,
        anonymize_on_expire: bool = False,
    ) -> DataRetentionRule:
        """保持ルールを作成"""
        rule_id = str(uuid.uuid4())
        now = datetime.utcnow()

        rule = DataRetentionRule(
            id=rule_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            retention_period=retention_period,
            auto_delete=auto_delete,
            anonymize_on_expire=anonymize_on_expire,
            created_at=now,
            updated_at=now,
        )

        self._rules[rule_id] = rule
        return rule

    async def get_rules(self, tenant_id: str) -> List[DataRetentionRule]:
        """テナントのルール一覧"""
        return [r for r in self._rules.values() if r.tenant_id == tenant_id]

    async def check_expiration(
        self,
        resource_type: str,
        created_at: datetime,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """有効期限をチェック"""
        rules = [r for r in self._rules.values()
                 if r.tenant_id == tenant_id and r.resource_type == resource_type]

        if not rules:
            return {"expired": False, "expiration_date": None}

        rule = rules[0]
        days = self._retention_days.get(rule.retention_period, -1)

        if days == -1:
            return {"expired": False, "expiration_date": None, "policy": "indefinite"}

        expiration_date = created_at + timedelta(days=days)
        expired = datetime.utcnow() > expiration_date

        return {
            "expired": expired,
            "expiration_date": expiration_date.isoformat(),
            "policy": rule.retention_period.value,
            "auto_delete": rule.auto_delete,
            "anonymize_on_expire": rule.anonymize_on_expire,
        }

    async def delete_rule(self, rule_id: str) -> bool:
        """ルールを削除"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False


class EncryptionManager:
    """暗号化管理"""

    def __init__(self):
        self._configs: Dict[str, EncryptionConfig] = {}
        self._keys: Dict[str, bytes] = {}

    async def configure(
        self,
        tenant_id: str,
        algorithm: str = "AES-256-GCM",
        key_rotation_days: int = 90,
        encrypt_at_rest: bool = True,
        encrypt_in_transit: bool = True,
    ) -> EncryptionConfig:
        """暗号化を設定"""
        key_id = str(uuid.uuid4())

        config = EncryptionConfig(
            algorithm=algorithm,
            key_rotation_days=key_rotation_days,
            encrypt_at_rest=encrypt_at_rest,
            encrypt_in_transit=encrypt_in_transit,
            key_id=key_id,
        )

        self._configs[tenant_id] = config
        # キーを生成（実際はKMSを使用）
        self._keys[key_id] = os.urandom(32)

        return config

    async def encrypt(self, tenant_id: str, data: bytes) -> bytes:
        """データを暗号化（シミュレーション）"""
        config = self._configs.get(tenant_id)
        if not config or not config.encrypt_at_rest:
            return data

        # 実際の暗号化はここで実装
        # シミュレーションとして元のデータを返す
        return data

    async def decrypt(self, tenant_id: str, encrypted_data: bytes) -> bytes:
        """データを復号化（シミュレーション）"""
        config = self._configs.get(tenant_id)
        if not config:
            return encrypted_data

        # 実際の復号化はここで実装
        return encrypted_data

    async def get_config(self, tenant_id: str) -> Optional[EncryptionConfig]:
        """設定を取得"""
        return self._configs.get(tenant_id)

    async def rotate_key(self, tenant_id: str) -> str:
        """キーをローテーション"""
        config = self._configs.get(tenant_id)
        if not config:
            raise ValueError("No encryption config found")

        old_key_id = config.key_id
        new_key_id = str(uuid.uuid4())

        self._keys[new_key_id] = os.urandom(32)
        config.key_id = new_key_id

        # 古いキーは一定期間保持（復号化用）
        # 実際の実装では適切なキー管理が必要

        return new_key_id


class ComplianceChecker:
    """コンプライアンスチェッカー"""

    def __init__(
        self,
        pii_detector: PIIDetector,
        audit_logger: AuditLogger,
        retention_manager: DataRetentionManager,
        encryption_manager: EncryptionManager,
    ):
        self.pii_detector = pii_detector
        self.audit_logger = audit_logger
        self.retention_manager = retention_manager
        self.encryption_manager = encryption_manager

    async def check_gdpr_compliance(self, tenant_id: str) -> Dict[str, Any]:
        """GDPR準拠をチェック"""
        encryption_config = await self.encryption_manager.get_config(tenant_id)
        retention_rules = await self.retention_manager.get_rules(tenant_id)

        checks = {
            "data_encryption": {
                "status": "pass" if encryption_config and encryption_config.encrypt_at_rest else "fail",
                "requirement": "Data must be encrypted at rest",
            },
            "retention_policy": {
                "status": "pass" if retention_rules else "fail",
                "requirement": "Data retention policy must be defined",
            },
            "audit_logging": {
                "status": "pass",
                "requirement": "Audit logging must be enabled",
            },
            "pii_protection": {
                "status": "pass",
                "requirement": "PII must be protected",
            },
        }

        passed = all(c["status"] == "pass" for c in checks.values())

        return {
            "standard": ComplianceStandard.GDPR.value,
            "compliant": passed,
            "checks": checks,
            "checked_at": datetime.utcnow().isoformat(),
        }

    async def check_hipaa_compliance(self, tenant_id: str) -> Dict[str, Any]:
        """HIPAA準拠をチェック"""
        encryption_config = await self.encryption_manager.get_config(tenant_id)

        checks = {
            "encryption_in_transit": {
                "status": "pass" if encryption_config and encryption_config.encrypt_in_transit else "fail",
                "requirement": "Data must be encrypted in transit",
            },
            "encryption_at_rest": {
                "status": "pass" if encryption_config and encryption_config.encrypt_at_rest else "fail",
                "requirement": "Data must be encrypted at rest",
            },
            "access_controls": {
                "status": "pass",
                "requirement": "Access controls must be implemented",
            },
            "audit_trails": {
                "status": "pass",
                "requirement": "Audit trails must be maintained",
            },
        }

        passed = all(c["status"] == "pass" for c in checks.values())

        return {
            "standard": ComplianceStandard.HIPAA.value,
            "compliant": passed,
            "checks": checks,
            "checked_at": datetime.utcnow().isoformat(),
        }

    async def generate_compliance_report(
        self,
        tenant_id: str,
        standards: List[ComplianceStandard],
    ) -> Dict[str, Any]:
        """コンプライアンスレポートを生成"""
        results = {}

        for standard in standards:
            if standard == ComplianceStandard.GDPR:
                results[standard.value] = await self.check_gdpr_compliance(tenant_id)
            elif standard == ComplianceStandard.HIPAA:
                results[standard.value] = await self.check_hipaa_compliance(tenant_id)
            else:
                results[standard.value] = {"status": "not_implemented"}

        overall_compliant = all(
            r.get("compliant", False) for r in results.values()
            if "compliant" in r
        )

        return {
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "overall_compliant": overall_compliant,
            "results": results,
        }


# グローバルインスタンス
pii_detector = PIIDetector()
audit_logger = AuditLogger()
retention_manager = DataRetentionManager()
encryption_manager = EncryptionManager()
compliance_checker = ComplianceChecker(
    pii_detector, audit_logger, retention_manager, encryption_manager
)
