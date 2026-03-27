"""Google Drive/Docs連携APIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services.google_integration_service import (
    google_auth_manager,
    google_drive_service,
    google_docs_service,
    transcription_exporter,
    auto_sync_manager,
    ExportFormat,
)

router = APIRouter(prefix="/google", tags=["google"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tenant_id() -> str:
    return "default-tenant"


# === OAuth認証 ===

@router.get("/auth/url")
async def get_auth_url(
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Google OAuth認証URLを取得"""
    auth_url = google_auth_manager.get_auth_url(
        redirect_uri=redirect_uri,
        state=state,
    )

    return {
        "auth_url": auth_url,
        "scopes": [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/documents",
        ],
    }


class ExchangeCodeRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/auth/callback")
async def exchange_auth_code(
    request: ExchangeCodeRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """認証コードをトークンに交換"""
    try:
        credentials = await google_auth_manager.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
        )

        google_auth_manager.store_credentials(tenant_id, credentials)

        return {
            "status": "authenticated",
            "scopes": credentials.scopes,
            "expires_at": credentials.token_expiry.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/auth/status")
async def get_auth_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """認証ステータスを取得"""
    credentials = google_auth_manager.get_credentials(tenant_id)

    if not credentials:
        return {
            "authenticated": False,
            "message": "Not connected to Google",
        }

    return {
        "authenticated": True,
        "scopes": credentials.scopes,
        "expires_at": credentials.token_expiry.isoformat(),
    }


@router.post("/auth/revoke")
async def revoke_auth(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """認証を取り消し"""
    success = await google_auth_manager.revoke_credentials(tenant_id)

    if not success:
        raise HTTPException(status_code=404, detail="No credentials found")

    return {
        "status": "revoked",
        "message": "Google connection has been removed",
    }


# === Google Drive ===

@router.get("/drive/files")
async def list_drive_files(
    folder_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Driveファイル一覧"""
    try:
        files = await google_drive_service.list_files(
            tenant_id=tenant_id,
            folder_id=folder_id,
            mime_type=mime_type,
            query=query,
            limit=limit,
        )

        return {
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "size": f.size,
                    "created_time": f.created_time.isoformat(),
                    "modified_time": f.modified_time.isoformat(),
                    "web_view_link": f.web_view_link,
                    "shared": f.shared,
                }
                for f in files
            ],
            "count": len(files),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None


@router.post("/drive/folders")
async def create_folder(
    request: CreateFolderRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """フォルダを作成"""
    try:
        folder = await google_drive_service.create_folder(
            tenant_id=tenant_id,
            name=request.name,
            parent_id=request.parent_id,
        )

        return {
            "id": folder.id,
            "name": folder.name,
            "web_view_link": folder.web_view_link,
            "created_time": folder.created_time.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class UploadFileRequest(BaseModel):
    name: str
    content: str  # base64 encoded
    mime_type: str
    folder_id: Optional[str] = None
    convert_to_google_format: bool = False


@router.post("/drive/upload")
async def upload_file(
    request: UploadFileRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ファイルをアップロード"""
    import base64

    try:
        content = base64.b64decode(request.content)
        file = await google_drive_service.upload_file(
            tenant_id=tenant_id,
            name=request.name,
            content=content,
            mime_type=request.mime_type,
            folder_id=request.folder_id,
            convert_to_google_format=request.convert_to_google_format,
        )

        return {
            "id": file.id,
            "name": file.name,
            "mime_type": file.mime_type,
            "size": file.size,
            "web_view_link": file.web_view_link,
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.delete("/drive/files/{file_id}")
async def delete_file(
    file_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ファイルを削除"""
    try:
        success = await google_drive_service.delete_file(
            tenant_id=tenant_id,
            file_id=file_id,
        )

        if not success:
            raise HTTPException(status_code=404, detail="File not found")

        return {"status": "deleted", "file_id": file_id}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class ShareFileRequest(BaseModel):
    email: str
    role: str = "reader"


@router.post("/drive/files/{file_id}/share")
async def share_file(
    file_id: str,
    request: ShareFileRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ファイルを共有"""
    try:
        result = await google_drive_service.share_file(
            tenant_id=tenant_id,
            file_id=file_id,
            email=request.email,
            role=request.role,
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Google Docs ===

class CreateDocRequest(BaseModel):
    title: str
    content: str = ""
    folder_id: Optional[str] = None


@router.post("/docs")
async def create_document(
    request: CreateDocRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Googleドキュメントを作成"""
    try:
        doc = await google_docs_service.create_document(
            tenant_id=tenant_id,
            title=request.title,
            content=request.content,
            folder_id=request.folder_id,
        )

        return {
            "id": doc.id,
            "title": doc.title,
            "web_view_link": doc.web_view_link,
            "created_time": doc.created_time.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/docs/{document_id}")
async def get_document(
    document_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ドキュメントを取得"""
    try:
        doc = await google_docs_service.get_document(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "id": doc.id,
            "title": doc.title,
            "content": doc.content,
            "revision_id": doc.revision_id,
            "web_view_link": doc.web_view_link,
            "modified_time": doc.modified_time.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


class UpdateDocRequest(BaseModel):
    content: str
    append: bool = False


@router.put("/docs/{document_id}")
async def update_document(
    document_id: str,
    request: UpdateDocRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """ドキュメントを更新"""
    try:
        doc = await google_docs_service.update_document(
            tenant_id=tenant_id,
            document_id=document_id,
            content=request.content,
            append=request.append,
        )

        return {
            "id": doc.id,
            "title": doc.title,
            "revision_id": doc.revision_id,
            "modified_time": doc.modified_time.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === エクスポート ===

class ExportTranscriptionRequest(BaseModel):
    transcription_id: str
    title: Optional[str] = None
    folder_id: Optional[str] = None
    format: str = "google_docs"


@router.post("/export/transcription")
async def export_transcription(
    request: ExportTranscriptionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """文字起こしをGoogleにエクスポート"""
    # 実際の実装ではDBから文字起こしを取得
    transcription_data = {
        "id": request.transcription_id,
        "title": request.title or "文字起こし",
        "segments": [
            {"text": "サンプルの文字起こしテキストです。", "speaker_id": "話者1"},
            {"text": "これはテスト用のデータです。", "speaker_id": "話者2"},
        ],
    }

    try:
        if request.format == "google_docs":
            doc = await transcription_exporter.export_to_google_docs(
                tenant_id=tenant_id,
                transcription_data=transcription_data,
                folder_id=request.folder_id,
            )

            return {
                "type": "google_docs",
                "id": doc.id,
                "title": doc.title,
                "web_view_link": doc.web_view_link,
            }
        else:
            export_format = ExportFormat(request.format)
            file = await transcription_exporter.export_to_drive(
                tenant_id=tenant_id,
                transcription_data=transcription_data,
                format=export_format,
                folder_id=request.folder_id,
            )

            return {
                "type": "drive_file",
                "id": file.id,
                "name": file.name,
                "web_view_link": file.web_view_link,
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExportMinutesRequest(BaseModel):
    transcription_id: str
    folder_id: Optional[str] = None


@router.post("/export/meeting-minutes")
async def export_meeting_minutes(
    request: ExportMinutesRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """議事録をGoogleにエクスポート"""
    # 実際の実装ではDBから議事録を取得
    minutes_data = {
        "title": "週次ミーティング議事録",
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "attendees": ["田中", "佐藤", "鈴木"],
        "agenda": ["進捗報告", "課題共有"],
        "discussion_points": [
            {"topic": "プロジェクト進捗", "details": "順調に進行中"},
        ],
        "decisions": ["次回は来週月曜開催"],
        "action_items": [
            {"task": "資料作成", "assignee": "田中", "deadline": "金曜日"},
        ],
        "summary": "生産的な会議でした。",
    }

    try:
        doc = await transcription_exporter.export_meeting_minutes_to_docs(
            tenant_id=tenant_id,
            minutes_data=minutes_data,
            folder_id=request.folder_id,
        )

        return {
            "id": doc.id,
            "title": doc.title,
            "web_view_link": doc.web_view_link,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === 自動同期 ===

class SetupAutoSyncRequest(BaseModel):
    resource_type: str
    folder_id: str
    sync_direction: str = "upload"
    format: str = "google_docs"


@router.post("/sync/setup")
async def setup_auto_sync(
    request: SetupAutoSyncRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """自動同期を設定"""
    try:
        export_format = ExportFormat(request.format)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid format: {request.format}")

    config = await auto_sync_manager.setup_auto_sync(
        tenant_id=tenant_id,
        resource_type=request.resource_type,
        folder_id=request.folder_id,
        sync_direction=request.sync_direction,
        format=export_format,
    )

    return {
        "status": "configured",
        "resource_type": config["resource_type"],
        "folder_id": config["folder_id"],
        "sync_direction": config["sync_direction"],
        "format": config["format"].value,
    }


@router.get("/sync/config")
async def get_sync_configs(
    resource_type: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """同期設定一覧"""
    if resource_type:
        config = await auto_sync_manager.get_sync_config(tenant_id, resource_type)
        if not config:
            return {"configs": [], "count": 0}
        configs = [config]
    else:
        # 全設定を取得
        configs = []
        for rt in ["transcription", "meeting_minutes", "summary"]:
            cfg = await auto_sync_manager.get_sync_config(tenant_id, rt)
            if cfg:
                configs.append(cfg)

    return {
        "configs": [
            {
                "resource_type": c["resource_type"],
                "folder_id": c["folder_id"],
                "sync_direction": c["sync_direction"],
                "format": c["format"].value if hasattr(c["format"], "value") else c["format"],
                "enabled": c["enabled"],
            }
            for c in configs
        ],
        "count": len(configs),
    }


@router.delete("/sync/config/{resource_type}")
async def disable_auto_sync(
    resource_type: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """自動同期を無効化"""
    success = await auto_sync_manager.disable_auto_sync(tenant_id, resource_type)

    if not success:
        raise HTTPException(status_code=404, detail="Sync config not found")

    return {
        "status": "disabled",
        "resource_type": resource_type,
    }


class SyncResourceRequest(BaseModel):
    resource_type: str
    resource_id: str
    resource_data: dict


@router.post("/sync/now")
async def sync_resource_now(
    request: SyncResourceRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """リソースを今すぐ同期"""
    try:
        status = await auto_sync_manager.sync_resource(
            tenant_id=tenant_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            resource_data=request.resource_data,
        )

        return {
            "sync_id": status.id,
            "status": status.status,
            "google_file_id": status.google_file_id,
            "last_sync": status.last_sync.isoformat(),
            "error_message": status.error_message,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sync/status")
async def get_sync_statuses(
    resource_type: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """同期ステータス一覧"""
    statuses = await auto_sync_manager.list_sync_statuses(
        tenant_id=tenant_id,
        resource_type=resource_type,
    )

    return {
        "statuses": [
            {
                "id": s.id,
                "resource_type": s.resource_type,
                "resource_id": s.resource_id,
                "google_file_id": s.google_file_id,
                "status": s.status,
                "last_sync": s.last_sync.isoformat(),
                "error_message": s.error_message,
            }
            for s in statuses
        ],
        "count": len(statuses),
    }


# === 利用可能なフォーマット ===

@router.get("/formats")
async def list_export_formats():
    """エクスポートフォーマット一覧"""
    return {
        "formats": [
            {"id": "google_docs", "name": "Google ドキュメント", "extension": None},
            {"id": "google_sheets", "name": "Google スプレッドシート", "extension": None},
            {"id": "google_slides", "name": "Google スライド", "extension": None},
            {"id": "pdf", "name": "PDF", "extension": ".pdf"},
            {"id": "docx", "name": "Word文書", "extension": ".docx"},
            {"id": "txt", "name": "テキストファイル", "extension": ".txt"},
            {"id": "md", "name": "Markdown", "extension": ".md"},
        ]
    }
