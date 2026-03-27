"""セキュリティ・コンプライアンスサービス"""

import os
import hashlib
import hmac
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import get_settings

settings = get_settings()


class DataClassification(str, Enum):
    """データ分類"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ComplianceFramework(str, Enum):
    """コンプライアンスフレームワーク"""
    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    PCI_DSS = "pci_dss"


class RetentionPolicy(BaseModel):
    """データ保持ポリシー"""
    policy_id: str
    name: str
    description: str
    retention_days: int
    data_types: List[str]
    auto_delete: bool
    archive_before_delete: bool
    compliance_frameworks: List[str]


@dataclass
class AccessLog:
    """アクセスログ"""
    id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    ip_address: str
    user_agent: str
    timestamp: str
    success: bool
    details: Dict[str, Any]


@dataclass
class SecurityAlert:
    """セキュリティアラート"""
    id: str
    alert_type: str
    severity: str  # low, medium, high, critical
    title: str
    description: str
    user_id: Optional[str]
    resource_id: Optional[str]
    timestamp: str
    resolved: bool
    resolved_at: Optional[str]


class EncryptionService:
    """暗号化サービス"""

    def __init__(self):
        self.master_key = getattr(settings, 'encryption_master_key', None)
        if not self.master_key:
            # 開発用のデフォルトキー（本番では環境変数から取得）
            self.master_key = base64.urlsafe_b64encode(os.urandom(32))

    def _derive_key(self, salt: bytes) -> bytes:
        """キー導出"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        return base64.urlsafe_b64encode(kdf.derive(self.master_key))

    def encrypt(self, data: str, context: Optional[str] = None) -> Dict[str, str]:
        """データを暗号化"""
        salt = os.urandom(16)
        key = self._derive_key(salt)
        fernet = Fernet(key)

        encrypted = fernet.encrypt(data.encode())

        return {
            "ciphertext": base64.urlsafe_b64encode(encrypted).decode(),
            "salt": base64.urlsafe_b64encode(salt).decode(),
            "context": context,
            "algorithm": "AES-256-GCM",
            "version": "1",
        }

    def decrypt(self, encrypted_data: Dict[str, str]) -> str:
        """データを復号"""
        salt = base64.urlsafe_b64decode(encrypted_data["salt"])
        ciphertext = base64.urlsafe_b64decode(encrypted_data["ciphertext"])

        key = self._derive_key(salt)
        fernet = Fernet(key)

        decrypted = fernet.decrypt(ciphertext)
        return decrypted.decode()

    def encrypt_file(self, file_path: str, output_path: str) -> Dict[str, str]:
        """ファイルを暗号化"""
        with open(file_path, "rb") as f:
            data = f.read()

        salt = os.urandom(16)
        key = self._derive_key(salt)
        fernet = Fernet(key)

        encrypted = fernet.encrypt(data)

        with open(output_path, "wb") as f:
            f.write(encrypted)

        return {
            "salt": base64.urlsafe_b64encode(salt).decode(),
            "original_size": len(data),
            "encrypted_size": len(encrypted),
        }

    def decrypt_file(self, encrypted_path: str, output_path: str, salt: str) -> bool:
        """ファイルを復号"""
        with open(encrypted_path, "rb") as f:
            encrypted_data = f.read()

        salt_bytes = base64.urlsafe_b64decode(salt)
        key = self._derive_key(salt_bytes)
        fernet = Fernet(key)

        decrypted = fernet.decrypt(encrypted_data)

        with open(output_path, "wb") as f:
            f.write(decrypted)

        return True


class DataRetentionService:
    """データ保持サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_policy(
        self,
        name: str,
        retention_days: int,
        data_types: List[str],
        auto_delete: bool = True,
        archive_before_delete: bool = True,
        compliance_frameworks: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> RetentionPolicy:
        """保持ポリシーを作成"""
        policy_id = str(uuid4())

        await self.db.execute(
            text("""
                INSERT INTO retention_policies (id, name, description, retention_days, data_types, auto_delete, archive_before_delete, compliance_frameworks, created_at)
                VALUES (:id, :name, :description, :retention_days, :data_types, :auto_delete, :archive_before_delete, :compliance_frameworks, :created_at)
            """),
            {
                "id": policy_id,
                "name": name,
                "description": description or "",
                "retention_days": retention_days,
                "data_types": json.dumps(data_types),
                "auto_delete": auto_delete,
                "archive_before_delete": archive_before_delete,
                "compliance_frameworks": json.dumps(compliance_frameworks or []),
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        await self.db.commit()

        return RetentionPolicy(
            policy_id=policy_id,
            name=name,
            description=description or "",
            retention_days=retention_days,
            data_types=data_types,
            auto_delete=auto_delete,
            archive_before_delete=archive_before_delete,
            compliance_frameworks=compliance_frameworks or [],
        )

    async def get_policies(self) -> List[RetentionPolicy]:
        """保持ポリシー一覧を取得"""
        result = await self.db.execute(
            text("SELECT id, name, description, retention_days, data_types, auto_delete, archive_before_delete, compliance_frameworks FROM retention_policies")
        )
        rows = result.fetchall()

        return [
            RetentionPolicy(
                policy_id=row[0],
                name=row[1],
                description=row[2],
                retention_days=row[3],
                data_types=json.loads(row[4]),
                auto_delete=row[5],
                archive_before_delete=row[6],
                compliance_frameworks=json.loads(row[7]),
            )
            for row in rows
        ]

    async def apply_retention_policies(self) -> Dict[str, int]:
        """保持ポリシーを適用（定期実行）"""
        policies = await self.get_policies()
        deleted_counts = {}

        for policy in policies:
            if not policy.auto_delete:
                continue

            cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)

            for data_type in policy.data_types:
                if data_type == "transcriptions":
                    # アーカイブ
                    if policy.archive_before_delete:
                        await self._archive_transcriptions(cutoff_date)

                    # 削除
                    result = await self.db.execute(
                        text("""
                            DELETE FROM transcriptions
                            WHERE created_at < :cutoff_date
                            AND archived = false
                        """),
                        {"cutoff_date": cutoff_date},
                    )
                    deleted_counts[data_type] = result.rowcount

                elif data_type == "audit_logs":
                    result = await self.db.execute(
                        text("DELETE FROM audit_logs WHERE created_at < :cutoff_date"),
                        {"cutoff_date": cutoff_date},
                    )
                    deleted_counts[data_type] = result.rowcount

        await self.db.commit()
        return deleted_counts

    async def _archive_transcriptions(self, cutoff_date: datetime):
        """文字起こしをアーカイブ"""
        await self.db.execute(
            text("""
                UPDATE transcriptions
                SET archived = true, archived_at = :now
                WHERE created_at < :cutoff_date AND archived = false
            """),
            {"cutoff_date": cutoff_date, "now": datetime.utcnow()},
        )


class AccessControlService:
    """アクセス制御サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_permission(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        action: str,
    ) -> bool:
        """権限チェック"""
        # ユーザーのロールを取得
        result = await self.db.execute(
            text("""
                SELECT r.permissions
                FROM users u
                JOIN user_roles ur ON u.id = ur.user_id
                JOIN roles r ON ur.role_id = r.id
                WHERE u.id = :user_id
            """),
            {"user_id": str(user_id)},
        )
        rows = result.fetchall()

        for row in rows:
            permissions = json.loads(row[0]) if row[0] else []
            permission_key = f"{resource_type}:{action}"

            if permission_key in permissions or f"{resource_type}:*" in permissions:
                return True

        # リソース固有の権限チェック
        if resource_type == "transcription":
            result = await self.db.execute(
                text("""
                    SELECT 1 FROM transcriptions
                    WHERE id = :resource_id AND (user_id = :user_id OR team_id IN (
                        SELECT team_id FROM team_members WHERE user_id = :user_id
                    ))
                """),
                {"resource_id": str(resource_id), "user_id": str(user_id)},
            )
            return result.fetchone() is not None

        return False

    async def log_access(
        self,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: Optional[UUID],
        ip_address: str,
        user_agent: str,
        success: bool,
        details: Optional[Dict] = None,
    ) -> AccessLog:
        """アクセスログを記録"""
        log_id = str(uuid4())
        now = datetime.utcnow().isoformat()

        await self.db.execute(
            text("""
                INSERT INTO access_logs (id, user_id, action, resource_type, resource_id, ip_address, user_agent, timestamp, success, details)
                VALUES (:id, :user_id, :action, :resource_type, :resource_id, :ip_address, :user_agent, :timestamp, :success, :details)
            """),
            {
                "id": log_id,
                "user_id": str(user_id),
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": now,
                "success": success,
                "details": json.dumps(details or {}),
            },
        )
        await self.db.commit()

        return AccessLog(
            id=log_id,
            user_id=str(user_id),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else "",
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=now,
            success=success,
            details=details or {},
        )

    async def get_access_logs(
        self,
        user_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AccessLog]:
        """アクセスログを取得"""
        query = "SELECT id, user_id, action, resource_type, resource_id, ip_address, user_agent, timestamp, success, details FROM access_logs WHERE 1=1"
        params: Dict[str, Any] = {"limit": limit}

        if user_id:
            query += " AND user_id = :user_id"
            params["user_id"] = str(user_id)
        if resource_type:
            query += " AND resource_type = :resource_type"
            params["resource_type"] = resource_type
        if action:
            query += " AND action = :action"
            params["action"] = action
        if start_date:
            query += " AND timestamp >= :start_date"
            params["start_date"] = start_date.isoformat()
        if end_date:
            query += " AND timestamp <= :end_date"
            params["end_date"] = end_date.isoformat()

        query += " ORDER BY timestamp DESC LIMIT :limit"

        result = await self.db.execute(text(query), params)
        rows = result.fetchall()

        return [
            AccessLog(
                id=row[0],
                user_id=row[1],
                action=row[2],
                resource_type=row[3],
                resource_id=row[4] or "",
                ip_address=row[5],
                user_agent=row[6],
                timestamp=row[7],
                success=row[8],
                details=json.loads(row[9]) if row[9] else {},
            )
            for row in rows
        ]


class SecurityAlertService:
    """セキュリティアラートサービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        user_id: Optional[UUID] = None,
        resource_id: Optional[UUID] = None,
    ) -> SecurityAlert:
        """アラートを作成"""
        alert_id = str(uuid4())
        now = datetime.utcnow().isoformat()

        await self.db.execute(
            text("""
                INSERT INTO security_alerts (id, alert_type, severity, title, description, user_id, resource_id, timestamp, resolved)
                VALUES (:id, :alert_type, :severity, :title, :description, :user_id, :resource_id, :timestamp, false)
            """),
            {
                "id": alert_id,
                "alert_type": alert_type,
                "severity": severity,
                "title": title,
                "description": description,
                "user_id": str(user_id) if user_id else None,
                "resource_id": str(resource_id) if resource_id else None,
                "timestamp": now,
            },
        )
        await self.db.commit()

        return SecurityAlert(
            id=alert_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            user_id=str(user_id) if user_id else None,
            resource_id=str(resource_id) if resource_id else None,
            timestamp=now,
            resolved=False,
            resolved_at=None,
        )

    async def detect_anomalies(self, user_id: UUID) -> List[SecurityAlert]:
        """異常検知"""
        alerts = []

        # 短時間での大量アクセス検出
        result = await self.db.execute(
            text("""
                SELECT COUNT(*) FROM access_logs
                WHERE user_id = :user_id
                AND timestamp > :threshold
            """),
            {
                "user_id": str(user_id),
                "threshold": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            },
        )
        access_count = result.scalar() or 0

        if access_count > 100:
            alert = await self.create_alert(
                alert_type="rate_limit",
                severity="high",
                title="異常なアクセス頻度",
                description=f"5分間で{access_count}回のアクセスを検出",
                user_id=user_id,
            )
            alerts.append(alert)

        # 失敗したログイン試行
        result = await self.db.execute(
            text("""
                SELECT COUNT(*) FROM access_logs
                WHERE user_id = :user_id
                AND action = 'login'
                AND success = false
                AND timestamp > :threshold
            """),
            {
                "user_id": str(user_id),
                "threshold": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            },
        )
        failed_logins = result.scalar() or 0

        if failed_logins >= 5:
            alert = await self.create_alert(
                alert_type="brute_force",
                severity="critical",
                title="ブルートフォース攻撃の可能性",
                description=f"1時間で{failed_logins}回のログイン失敗を検出",
                user_id=user_id,
            )
            alerts.append(alert)

        return alerts

    async def get_alerts(
        self,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        limit: int = 50,
    ) -> List[SecurityAlert]:
        """アラート一覧を取得"""
        query = "SELECT id, alert_type, severity, title, description, user_id, resource_id, timestamp, resolved, resolved_at FROM security_alerts WHERE 1=1"
        params: Dict[str, Any] = {"limit": limit}

        if severity:
            query += " AND severity = :severity"
            params["severity"] = severity
        if resolved is not None:
            query += " AND resolved = :resolved"
            params["resolved"] = resolved

        query += " ORDER BY timestamp DESC LIMIT :limit"

        result = await self.db.execute(text(query), params)
        rows = result.fetchall()

        return [
            SecurityAlert(
                id=row[0],
                alert_type=row[1],
                severity=row[2],
                title=row[3],
                description=row[4],
                user_id=row[5],
                resource_id=row[6],
                timestamp=row[7],
                resolved=row[8],
                resolved_at=row[9],
            )
            for row in rows
        ]


class GDPRService:
    """GDPR準拠サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption = EncryptionService()

    async def export_user_data(self, user_id: UUID) -> Dict[str, Any]:
        """ユーザーデータをエクスポート（データポータビリティ）"""
        data = {
            "export_date": datetime.utcnow().isoformat(),
            "user_id": str(user_id),
        }

        # ユーザー情報
        result = await self.db.execute(
            text("SELECT email, name, created_at FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
        user_row = result.fetchone()
        if user_row:
            data["user_info"] = {
                "email": user_row[0],
                "name": user_row[1],
                "created_at": user_row[2],
            }

        # 文字起こし
        result = await self.db.execute(
            text("SELECT id, title, created_at FROM transcriptions WHERE user_id = :id"),
            {"id": str(user_id)},
        )
        data["transcriptions"] = [
            {"id": row[0], "title": row[1], "created_at": row[2]}
            for row in result.fetchall()
        ]

        # アクセスログ
        result = await self.db.execute(
            text("SELECT action, timestamp, ip_address FROM access_logs WHERE user_id = :id ORDER BY timestamp DESC LIMIT 100"),
            {"id": str(user_id)},
        )
        data["access_logs"] = [
            {"action": row[0], "timestamp": row[1], "ip_address": row[2]}
            for row in result.fetchall()
        ]

        return data

    async def delete_user_data(self, user_id: UUID, retain_anonymized: bool = False) -> Dict[str, int]:
        """ユーザーデータを削除（忘れられる権利）"""
        deleted_counts = {}

        if retain_anonymized:
            # 匿名化
            await self.db.execute(
                text("""
                    UPDATE transcriptions
                    SET user_id = NULL, title = 'Anonymized'
                    WHERE user_id = :id
                """),
                {"id": str(user_id)},
            )
        else:
            # 完全削除
            result = await self.db.execute(
                text("DELETE FROM transcriptions WHERE user_id = :id"),
                {"id": str(user_id)},
            )
            deleted_counts["transcriptions"] = result.rowcount

        # アクセスログを匿名化
        await self.db.execute(
            text("""
                UPDATE access_logs
                SET user_id = 'anonymized', ip_address = 'anonymized'
                WHERE user_id = :id
            """),
            {"id": str(user_id)},
        )

        # ユーザー削除
        result = await self.db.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
        deleted_counts["users"] = result.rowcount

        await self.db.commit()
        return deleted_counts

    async def record_consent(
        self,
        user_id: UUID,
        consent_type: str,
        granted: bool,
        ip_address: str,
    ) -> str:
        """同意を記録"""
        consent_id = str(uuid4())

        await self.db.execute(
            text("""
                INSERT INTO consent_records (id, user_id, consent_type, granted, ip_address, timestamp)
                VALUES (:id, :user_id, :consent_type, :granted, :ip_address, :timestamp)
            """),
            {
                "id": consent_id,
                "user_id": str(user_id),
                "consent_type": consent_type,
                "granted": granted,
                "ip_address": ip_address,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        await self.db.commit()

        return consent_id
