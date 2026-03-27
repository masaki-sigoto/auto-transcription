"""Google Drive/Docs連携サービス"""

import os
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import json


class GoogleService(str, Enum):
    DRIVE = "drive"
    DOCS = "docs"
    SHEETS = "sheets"
    SLIDES = "slides"


class ExportFormat(str, Enum):
    GOOGLE_DOCS = "google_docs"
    GOOGLE_SHEETS = "google_sheets"
    GOOGLE_SLIDES = "google_slides"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


@dataclass
class GoogleCredentials:
    """Google認証情報"""
    access_token: str
    refresh_token: str
    token_expiry: datetime
    scopes: List[str]


@dataclass
class DriveFile:
    """Driveファイル"""
    id: str
    name: str
    mime_type: str
    size: int
    created_time: datetime
    modified_time: datetime
    web_view_link: str
    download_link: Optional[str] = None
    parent_id: Optional[str] = None
    shared: bool = False


@dataclass
class GoogleDoc:
    """Google Docsドキュメント"""
    id: str
    title: str
    content: str
    revision_id: str
    created_time: datetime
    modified_time: datetime
    web_view_link: str


@dataclass
class SyncStatus:
    """同期ステータス"""
    id: str
    resource_type: str
    resource_id: str
    google_file_id: str
    last_sync: datetime
    sync_direction: str  # upload, download, bidirectional
    status: str  # synced, pending, error
    error_message: Optional[str] = None


class GoogleAuthManager:
    """Google認証管理"""

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self._credentials: Dict[str, GoogleCredentials] = {}

    def get_auth_url(
        self,
        redirect_uri: str,
        scopes: List[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """OAuth認証URLを生成"""
        scopes = scopes or [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/documents",
        ]

        # シミュレーション
        scope_str = " ".join(scopes)
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_str}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        if state:
            auth_url += f"&state={state}"

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> GoogleCredentials:
        """認証コードをトークンに交換"""
        # シミュレーション（実際はGoogle OAuth APIを呼び出す）
        credentials = GoogleCredentials(
            access_token=f"access_{uuid.uuid4().hex[:16]}",
            refresh_token=f"refresh_{uuid.uuid4().hex[:16]}",
            token_expiry=datetime.utcnow(),
            scopes=[
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/documents",
            ],
        )

        return credentials

    async def refresh_token(
        self,
        tenant_id: str,
    ) -> GoogleCredentials:
        """トークンをリフレッシュ"""
        if tenant_id not in self._credentials:
            raise ValueError("No credentials found for tenant")

        old_creds = self._credentials[tenant_id]

        # シミュレーション
        new_creds = GoogleCredentials(
            access_token=f"access_{uuid.uuid4().hex[:16]}",
            refresh_token=old_creds.refresh_token,
            token_expiry=datetime.utcnow(),
            scopes=old_creds.scopes,
        )

        self._credentials[tenant_id] = new_creds
        return new_creds

    def store_credentials(
        self,
        tenant_id: str,
        credentials: GoogleCredentials,
    ):
        """認証情報を保存"""
        self._credentials[tenant_id] = credentials

    def get_credentials(
        self,
        tenant_id: str,
    ) -> Optional[GoogleCredentials]:
        """認証情報を取得"""
        return self._credentials.get(tenant_id)

    async def revoke_credentials(
        self,
        tenant_id: str,
    ) -> bool:
        """認証を取り消し"""
        if tenant_id in self._credentials:
            del self._credentials[tenant_id]
            return True
        return False


class GoogleDriveService:
    """Google Driveサービス"""

    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self._files: Dict[str, DriveFile] = {}

    async def list_files(
        self,
        tenant_id: str,
        folder_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> List[DriveFile]:
        """ファイル一覧を取得"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        # シミュレーション
        files = list(self._files.values())

        if folder_id:
            files = [f for f in files if f.parent_id == folder_id]
        if mime_type:
            files = [f for f in files if f.mime_type == mime_type]

        return files[:limit]

    async def create_folder(
        self,
        tenant_id: str,
        name: str,
        parent_id: Optional[str] = None,
    ) -> DriveFile:
        """フォルダを作成"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        file_id = str(uuid.uuid4())
        folder = DriveFile(
            id=file_id,
            name=name,
            mime_type="application/vnd.google-apps.folder",
            size=0,
            created_time=datetime.utcnow(),
            modified_time=datetime.utcnow(),
            web_view_link=f"https://drive.google.com/drive/folders/{file_id}",
            parent_id=parent_id,
        )

        self._files[file_id] = folder
        return folder

    async def upload_file(
        self,
        tenant_id: str,
        name: str,
        content: bytes,
        mime_type: str,
        folder_id: Optional[str] = None,
        convert_to_google_format: bool = False,
    ) -> DriveFile:
        """ファイルをアップロード"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        file_id = str(uuid.uuid4())

        # Google形式に変換
        if convert_to_google_format:
            if mime_type in ["text/plain", "text/markdown", "application/msword"]:
                mime_type = "application/vnd.google-apps.document"
            elif mime_type in ["text/csv", "application/vnd.ms-excel"]:
                mime_type = "application/vnd.google-apps.spreadsheet"

        file = DriveFile(
            id=file_id,
            name=name,
            mime_type=mime_type,
            size=len(content),
            created_time=datetime.utcnow(),
            modified_time=datetime.utcnow(),
            web_view_link=f"https://drive.google.com/file/d/{file_id}/view",
            download_link=f"https://drive.google.com/uc?id={file_id}&export=download",
            parent_id=folder_id,
        )

        self._files[file_id] = file
        return file

    async def download_file(
        self,
        tenant_id: str,
        file_id: str,
        export_format: Optional[str] = None,
    ) -> bytes:
        """ファイルをダウンロード"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        if file_id not in self._files:
            raise ValueError("File not found")

        # シミュレーション
        return b"File content"

    async def delete_file(
        self,
        tenant_id: str,
        file_id: str,
    ) -> bool:
        """ファイルを削除"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        if file_id in self._files:
            del self._files[file_id]
            return True
        return False

    async def share_file(
        self,
        tenant_id: str,
        file_id: str,
        email: str,
        role: str = "reader",  # reader, writer, commenter
    ) -> Dict[str, Any]:
        """ファイルを共有"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        if file_id not in self._files:
            raise ValueError("File not found")

        self._files[file_id].shared = True

        return {
            "file_id": file_id,
            "shared_with": email,
            "role": role,
            "link": self._files[file_id].web_view_link,
        }


class GoogleDocsService:
    """Google Docsサービス"""

    def __init__(self, auth_manager: GoogleAuthManager, drive_service: GoogleDriveService):
        self.auth_manager = auth_manager
        self.drive_service = drive_service
        self._docs: Dict[str, GoogleDoc] = {}

    async def create_document(
        self,
        tenant_id: str,
        title: str,
        content: str = "",
        folder_id: Optional[str] = None,
    ) -> GoogleDoc:
        """ドキュメントを作成"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        doc_id = str(uuid.uuid4())
        doc = GoogleDoc(
            id=doc_id,
            title=title,
            content=content,
            revision_id="1",
            created_time=datetime.utcnow(),
            modified_time=datetime.utcnow(),
            web_view_link=f"https://docs.google.com/document/d/{doc_id}/edit",
        )

        self._docs[doc_id] = doc

        # Driveにも登録
        drive_file = DriveFile(
            id=doc_id,
            name=title,
            mime_type="application/vnd.google-apps.document",
            size=len(content.encode()),
            created_time=doc.created_time,
            modified_time=doc.modified_time,
            web_view_link=doc.web_view_link,
            parent_id=folder_id,
        )
        self.drive_service._files[doc_id] = drive_file

        return doc

    async def get_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> Optional[GoogleDoc]:
        """ドキュメントを取得"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        return self._docs.get(document_id)

    async def update_document(
        self,
        tenant_id: str,
        document_id: str,
        content: str,
        append: bool = False,
    ) -> GoogleDoc:
        """ドキュメントを更新"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        if document_id not in self._docs:
            raise ValueError("Document not found")

        doc = self._docs[document_id]

        if append:
            doc.content += "\n" + content
        else:
            doc.content = content

        doc.modified_time = datetime.utcnow()
        doc.revision_id = str(int(doc.revision_id) + 1)

        return doc

    async def insert_text(
        self,
        tenant_id: str,
        document_id: str,
        text: str,
        index: int = 0,
    ) -> GoogleDoc:
        """テキストを挿入"""
        creds = self.auth_manager.get_credentials(tenant_id)
        if not creds:
            raise ValueError("Not authenticated with Google")

        if document_id not in self._docs:
            raise ValueError("Document not found")

        doc = self._docs[document_id]
        doc.content = doc.content[:index] + text + doc.content[index:]
        doc.modified_time = datetime.utcnow()
        doc.revision_id = str(int(doc.revision_id) + 1)

        return doc


class TranscriptionExporter:
    """文字起こしエクスポーター"""

    def __init__(
        self,
        drive_service: GoogleDriveService,
        docs_service: GoogleDocsService,
    ):
        self.drive_service = drive_service
        self.docs_service = docs_service

    async def export_to_google_docs(
        self,
        tenant_id: str,
        transcription_data: Dict[str, Any],
        folder_id: Optional[str] = None,
        template: Optional[str] = None,
    ) -> GoogleDoc:
        """文字起こしをGoogle Docsにエクスポート"""
        # Markdownフォーマットで作成
        content = self._format_transcription(transcription_data, template)

        title = transcription_data.get("title", "文字起こし") + f" - {datetime.utcnow().strftime('%Y-%m-%d')}"

        doc = await self.docs_service.create_document(
            tenant_id=tenant_id,
            title=title,
            content=content,
            folder_id=folder_id,
        )

        return doc

    async def export_meeting_minutes_to_docs(
        self,
        tenant_id: str,
        minutes_data: Dict[str, Any],
        folder_id: Optional[str] = None,
    ) -> GoogleDoc:
        """議事録をGoogle Docsにエクスポート"""
        content = self._format_meeting_minutes(minutes_data)

        title = minutes_data.get("title", "議事録") + f" - {minutes_data.get('date', datetime.utcnow().strftime('%Y-%m-%d'))}"

        doc = await self.docs_service.create_document(
            tenant_id=tenant_id,
            title=title,
            content=content,
            folder_id=folder_id,
        )

        return doc

    async def export_to_drive(
        self,
        tenant_id: str,
        transcription_data: Dict[str, Any],
        format: ExportFormat,
        folder_id: Optional[str] = None,
    ) -> DriveFile:
        """文字起こしをDriveにエクスポート"""
        content = self._format_transcription(transcription_data)
        title = transcription_data.get("title", "文字起こし")

        if format == ExportFormat.TXT:
            file_name = f"{title}.txt"
            mime_type = "text/plain"
            file_content = content.encode()
        elif format == ExportFormat.MD:
            file_name = f"{title}.md"
            mime_type = "text/markdown"
            file_content = content.encode()
        elif format == ExportFormat.GOOGLE_DOCS:
            file_name = f"{title}"
            mime_type = "text/plain"
            file_content = content.encode()
        else:
            file_name = f"{title}.txt"
            mime_type = "text/plain"
            file_content = content.encode()

        file = await self.drive_service.upload_file(
            tenant_id=tenant_id,
            name=file_name,
            content=file_content,
            mime_type=mime_type,
            folder_id=folder_id,
            convert_to_google_format=(format == ExportFormat.GOOGLE_DOCS),
        )

        return file

    def _format_transcription(
        self,
        transcription_data: Dict[str, Any],
        template: Optional[str] = None,
    ) -> str:
        """文字起こしをフォーマット"""
        lines = []
        lines.append(f"# {transcription_data.get('title', '文字起こし')}")
        lines.append("")
        lines.append(f"**作成日時**: {datetime.utcnow().strftime('%Y年%m月%d日 %H:%M')}")
        lines.append("")

        segments = transcription_data.get("segments", [])
        current_speaker = None

        for seg in segments:
            speaker = seg.get("speaker_id", "不明")
            text = seg.get("text", "")

            if speaker != current_speaker:
                lines.append("")
                lines.append(f"**{speaker}**:")
                current_speaker = speaker

            lines.append(text)

        return "\n".join(lines)

    def _format_meeting_minutes(self, minutes_data: Dict[str, Any]) -> str:
        """議事録をフォーマット"""
        lines = []
        lines.append(f"# {minutes_data.get('title', '議事録')}")
        lines.append("")
        lines.append(f"**日付**: {minutes_data.get('date', '')}")
        lines.append(f"**参加者**: {', '.join(minutes_data.get('attendees', []))}")
        lines.append("")

        lines.append("## 議題")
        for agenda in minutes_data.get("agenda", []):
            lines.append(f"- {agenda}")
        lines.append("")

        lines.append("## 議論内容")
        for point in minutes_data.get("discussion_points", []):
            lines.append(f"### {point.get('topic', '')}")
            lines.append(point.get("details", ""))
            lines.append("")

        lines.append("## 決定事項")
        for decision in minutes_data.get("decisions", []):
            lines.append(f"- {decision}")
        lines.append("")

        lines.append("## アクションアイテム")
        for item in minutes_data.get("action_items", []):
            lines.append(f"- [ ] {item.get('task', '')} (担当: {item.get('assignee', '')}, 期限: {item.get('deadline', '')})")
        lines.append("")

        lines.append("## まとめ")
        lines.append(minutes_data.get("summary", ""))

        return "\n".join(lines)


class AutoSyncManager:
    """自動同期マネージャー"""

    def __init__(
        self,
        drive_service: GoogleDriveService,
        docs_service: GoogleDocsService,
    ):
        self.drive_service = drive_service
        self.docs_service = docs_service
        self._sync_configs: Dict[str, Dict[str, Any]] = {}
        self._sync_statuses: Dict[str, SyncStatus] = {}

    async def setup_auto_sync(
        self,
        tenant_id: str,
        resource_type: str,  # transcription, meeting_minutes, etc.
        folder_id: str,
        sync_direction: str = "upload",
        format: ExportFormat = ExportFormat.GOOGLE_DOCS,
    ) -> Dict[str, Any]:
        """自動同期を設定"""
        config_id = f"{tenant_id}_{resource_type}"

        self._sync_configs[config_id] = {
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "folder_id": folder_id,
            "sync_direction": sync_direction,
            "format": format,
            "enabled": True,
            "created_at": datetime.utcnow(),
        }

        return self._sync_configs[config_id]

    async def get_sync_config(
        self,
        tenant_id: str,
        resource_type: str,
    ) -> Optional[Dict[str, Any]]:
        """同期設定を取得"""
        config_id = f"{tenant_id}_{resource_type}"
        return self._sync_configs.get(config_id)

    async def disable_auto_sync(
        self,
        tenant_id: str,
        resource_type: str,
    ) -> bool:
        """自動同期を無効化"""
        config_id = f"{tenant_id}_{resource_type}"
        if config_id in self._sync_configs:
            self._sync_configs[config_id]["enabled"] = False
            return True
        return False

    async def sync_resource(
        self,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        resource_data: Dict[str, Any],
    ) -> SyncStatus:
        """リソースを同期"""
        config_id = f"{tenant_id}_{resource_type}"
        config = self._sync_configs.get(config_id)

        if not config or not config["enabled"]:
            raise ValueError("Auto-sync not configured or disabled")

        status_id = str(uuid.uuid4())

        try:
            # Google Docsにエクスポート
            content = json.dumps(resource_data, ensure_ascii=False, indent=2)
            doc = await self.docs_service.create_document(
                tenant_id=tenant_id,
                title=f"{resource_type}_{resource_id}",
                content=content,
                folder_id=config["folder_id"],
            )

            status = SyncStatus(
                id=status_id,
                resource_type=resource_type,
                resource_id=resource_id,
                google_file_id=doc.id,
                last_sync=datetime.utcnow(),
                sync_direction=config["sync_direction"],
                status="synced",
            )

        except Exception as e:
            status = SyncStatus(
                id=status_id,
                resource_type=resource_type,
                resource_id=resource_id,
                google_file_id="",
                last_sync=datetime.utcnow(),
                sync_direction=config.get("sync_direction", "upload"),
                status="error",
                error_message=str(e),
            )

        self._sync_statuses[status_id] = status
        return status

    async def get_sync_status(
        self,
        tenant_id: str,
        resource_id: str,
    ) -> Optional[SyncStatus]:
        """同期ステータスを取得"""
        for status in self._sync_statuses.values():
            if status.resource_id == resource_id:
                return status
        return None

    async def list_sync_statuses(
        self,
        tenant_id: str,
        resource_type: Optional[str] = None,
    ) -> List[SyncStatus]:
        """同期ステータス一覧"""
        statuses = list(self._sync_statuses.values())

        if resource_type:
            statuses = [s for s in statuses if s.resource_type == resource_type]

        return statuses


# グローバルインスタンス
google_auth_manager = GoogleAuthManager()
google_drive_service = GoogleDriveService(google_auth_manager)
google_docs_service = GoogleDocsService(google_auth_manager, google_drive_service)
transcription_exporter = TranscriptionExporter(google_drive_service, google_docs_service)
auto_sync_manager = AutoSyncManager(google_drive_service, google_docs_service)
