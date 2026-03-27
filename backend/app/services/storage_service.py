"""ストレージサービス - S3またはローカルファイルシステム対応"""

import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import get_settings


class LocalStorageService:
    """ローカルファイルシステムストレージ"""

    def __init__(self, base_path: str = "/app/storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def generate_presigned_upload_url(
        self,
        file_extension: str,
        user_id: uuid.UUID,
        expires_in: int = 3600,
    ) -> dict:
        """
        ローカル用のアップロード情報を生成
        実際にはダイレクトアップロード用のエンドポイントパスを返す
        """
        file_key = f"uploads/{user_id}/{uuid.uuid4()}.{file_extension.lstrip('.')}"
        # ローカルの場合は直接アップロードAPIを使用
        return {"url": f"/api/v1/upload/direct", "key": file_key}

    def generate_presigned_download_url(
        self,
        file_key: str,
        expires_in: int = 3600,
    ) -> str:
        """ダウンロードURL生成（ローカルの場合はAPIエンドポイント）"""
        return f"/api/v1/upload/download/{file_key}"

    def download_file(self, file_key: str, local_path: str) -> str:
        """ローカルストレージからファイルをコピー"""
        source_path = self.base_path / file_key
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {file_key}")
        shutil.copy2(source_path, local_path)
        return local_path

    def upload_file(self, local_path: str, file_key: str) -> str:
        """ファイルをローカルストレージに保存"""
        dest_path = self.base_path / file_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest_path)
        return f"local://{file_key}"

    def save_uploaded_file(self, file_content: bytes, file_key: str) -> str:
        """アップロードされたファイルを直接保存"""
        dest_path = self.base_path / file_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(file_content)
        return f"local://{file_key}"

    def get_file_path(self, file_key: str) -> Path:
        """ファイルの実際のパスを取得"""
        return self.base_path / file_key

    def delete_file(self, file_key: str) -> bool:
        """ファイルを削除"""
        file_path = self.base_path / file_key
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def _get_content_type(self, file_extension: str) -> str:
        """ファイル拡張子からContent-Typeを取得"""
        content_types = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
            "webm": "audio/webm",
        }
        return content_types.get(file_extension.lstrip(".").lower(), "application/octet-stream")


class S3StorageService:
    """S3ストレージサービス"""

    def __init__(self):
        import boto3
        settings = get_settings()
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self.bucket_name = settings.s3_bucket_name

    def generate_presigned_upload_url(
        self,
        file_extension: str,
        user_id: uuid.UUID,
        expires_in: int = 3600,
    ) -> dict:
        """署名付きアップロードURLを生成"""
        from botocore.exceptions import ClientError

        file_key = f"uploads/{user_id}/{uuid.uuid4()}.{file_extension.lstrip('.')}"

        try:
            url = self.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": file_key,
                    "ContentType": self._get_content_type(file_extension),
                },
                ExpiresIn=expires_in,
            )
            return {"url": url, "key": file_key}
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    def generate_presigned_download_url(
        self,
        file_key: str,
        expires_in: int = 3600,
    ) -> str:
        """署名付きダウンロードURLを生成"""
        from botocore.exceptions import ClientError

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": file_key,
                },
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    def download_file(self, file_key: str, local_path: str) -> str:
        """S3からファイルをダウンロード"""
        from botocore.exceptions import ClientError

        try:
            self.s3_client.download_file(self.bucket_name, file_key, local_path)
            return local_path
        except ClientError as e:
            raise RuntimeError(f"Failed to download file: {e}")

    def upload_file(self, local_path: str, file_key: str) -> str:
        """ファイルをS3にアップロード"""
        from botocore.exceptions import ClientError

        try:
            self.s3_client.upload_file(local_path, self.bucket_name, file_key)
            return f"s3://{self.bucket_name}/{file_key}"
        except ClientError as e:
            raise RuntimeError(f"Failed to upload file: {e}")

    def delete_file(self, file_key: str) -> bool:
        """S3からファイルを削除"""
        from botocore.exceptions import ClientError

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError:
            return False

    def _get_content_type(self, file_extension: str) -> str:
        """ファイル拡張子からContent-Typeを取得"""
        content_types = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
            "webm": "audio/webm",
        }
        return content_types.get(file_extension.lstrip(".").lower(), "application/octet-stream")


class StorageService:
    """ストレージサービスのファクトリ"""

    def __init__(self):
        settings = get_settings()
        self.use_s3 = bool(settings.aws_access_key_id and settings.s3_bucket_name)

        if self.use_s3:
            self._service = S3StorageService()
        else:
            storage_path = os.getenv("LOCAL_STORAGE_PATH", "/app/storage")
            self._service = LocalStorageService(storage_path)

    def __getattr__(self, name):
        return getattr(self._service, name)
