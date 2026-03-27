"""ファイルアップロードAPI"""

import uuid
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.security import get_current_user
from app.models.user import User
from app.services.storage_service import StorageService, LocalStorageService

router = APIRouter(prefix="/upload", tags=["upload"])


class PresignedUrlResponse(BaseModel):
    upload_url: str
    file_key: str


class DirectUploadResponse(BaseModel):
    file_key: str
    audio_url: str


@router.post("/presigned", response_model=PresignedUrlResponse)
async def get_presigned_upload_url(
    file_extension: str = Query(..., description="ファイル拡張子 (例: mp3, wav)"),
    current_user: User = Depends(get_current_user),
):
    """署名付きアップロードURLを取得（S3使用時）"""
    storage = StorageService()
    result = storage.generate_presigned_upload_url(file_extension, current_user.id)

    return PresignedUrlResponse(
        upload_url=result["url"],
        file_key=result["key"],
    )


@router.post("/direct", response_model=DirectUploadResponse)
async def direct_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """ファイルを直接アップロード（ローカルストレージ使用時）"""
    # ファイル拡張子を取得
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed_extensions = {"mp3", "wav", "m4a", "flac", "ogg", "webm", "mp4"}

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
        )

    # ファイルキーを生成
    file_key = f"uploads/{current_user.id}/{uuid.uuid4()}.{extension}"

    # ファイルを保存
    storage = StorageService()
    content = await file.read()

    # ローカルストレージの場合は直接保存
    if hasattr(storage._service, 'save_uploaded_file'):
        audio_url = storage._service.save_uploaded_file(content, file_key)
    else:
        # S3の場合は一時ファイル経由
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            audio_url = storage.upload_file(tmp_path, file_key)
        finally:
            os.unlink(tmp_path)

    return DirectUploadResponse(
        file_key=file_key,
        audio_url=audio_url,
    )


@router.get("/download/{file_key:path}")
async def download_file(
    file_key: str,
    current_user: User = Depends(get_current_user),
):
    """ファイルをダウンロード（ローカルストレージ使用時）"""
    storage = StorageService()

    # ローカルストレージの場合のみ対応
    if not isinstance(storage._service, LocalStorageService):
        raise HTTPException(
            status_code=400,
            detail="Direct download only available for local storage"
        )

    # ユーザーが自分のファイルのみダウンロード可能
    if not file_key.startswith(f"uploads/{current_user.id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = storage._service.get_file_path(file_key)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Content-Typeを判定
    extension = file_key.rsplit(".", 1)[-1].lower()
    content_type = storage._service._get_content_type(extension)

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=file_path.name,
    )
