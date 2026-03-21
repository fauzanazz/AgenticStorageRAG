"""Supabase Storage client wrapper.

Handles file upload, download, and deletion with 7-day TTL lifecycle
for user-uploaded documents. In local dev, falls back to local filesystem
or a Supabase-compatible API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client as SupabaseClient
from supabase import create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Storage bucket names
DOCUMENTS_BUCKET = "documents"


class StorageClient:
    """Supabase Storage client for file management.

    Handles upload/download/delete with TTL tracking.
    The actual TTL enforcement is done by the expiry background job,
    not by Supabase lifecycle policies (which are limited).
    """

    def __init__(self) -> None:
        self._client: SupabaseClient | None = None

    def connect(self) -> None:
        """Initialize Supabase client."""
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            logger.warning("Supabase credentials not configured. Storage disabled.")
            return

        self._client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        logger.info("Supabase Storage connected: %s", settings.supabase_url)

    @property
    def client(self) -> SupabaseClient:
        """Get the Supabase client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Supabase Storage not connected. Call connect() first.")
        return self._client

    async def ensure_bucket(self, bucket_name: str = DOCUMENTS_BUCKET) -> None:
        """Ensure the storage bucket exists, creating it if needed."""
        try:
            self.client.storage.get_bucket(bucket_name)
        except Exception:
            self.client.storage.create_bucket(
                bucket_name,
                options={"public": False},
            )
            logger.info("Created storage bucket: %s", bucket_name)

    async def upload_file(
        self,
        file_path: str,
        file_content: bytes,
        content_type: str,
        bucket_name: str = DOCUMENTS_BUCKET,
    ) -> dict[str, Any]:
        """Upload a file to Supabase Storage.

        Args:
            file_path: Path within the bucket (e.g., "user_123/doc_456.pdf")
            file_content: Raw file bytes
            content_type: MIME type (e.g., "application/pdf")
            bucket_name: Target bucket name

        Returns:
            Upload response with path info
        """
        response = self.client.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": content_type},
        )
        logger.info("File uploaded: %s/%s", bucket_name, file_path)
        return {"path": file_path, "bucket": bucket_name, "response": str(response)}

    async def download_file(
        self,
        file_path: str,
        bucket_name: str = DOCUMENTS_BUCKET,
    ) -> bytes:
        """Download a file from Supabase Storage.

        Args:
            file_path: Path within the bucket
            bucket_name: Source bucket name

        Returns:
            Raw file bytes
        """
        response = self.client.storage.from_(bucket_name).download(file_path)
        return response

    async def delete_file(
        self,
        file_path: str,
        bucket_name: str = DOCUMENTS_BUCKET,
    ) -> None:
        """Delete a file from Supabase Storage.

        Args:
            file_path: Path within the bucket
            bucket_name: Source bucket name
        """
        self.client.storage.from_(bucket_name).remove([file_path])
        logger.info("File deleted: %s/%s", bucket_name, file_path)

    async def delete_files(
        self,
        file_paths: list[str],
        bucket_name: str = DOCUMENTS_BUCKET,
    ) -> None:
        """Delete multiple files from Supabase Storage."""
        if not file_paths:
            return
        self.client.storage.from_(bucket_name).remove(file_paths)
        logger.info("Deleted %d files from %s", len(file_paths), bucket_name)

    async def get_signed_url(
        self,
        file_path: str,
        expires_in: int = 3600,
        bucket_name: str = DOCUMENTS_BUCKET,
    ) -> str:
        """Generate a signed URL for temporary file access.

        Args:
            file_path: Path within the bucket
            expires_in: URL validity in seconds (default: 1 hour)
            bucket_name: Source bucket name

        Returns:
            Signed URL string
        """
        response = self.client.storage.from_(bucket_name).create_signed_url(file_path, expires_in)
        return response["signedURL"]

    @staticmethod
    def calculate_expiry(ttl_days: int | None = None) -> datetime:
        """Calculate expiry timestamp for a file.

        Args:
            ttl_days: Time-to-live in days. If None, uses config default.

        Returns:
            UTC datetime when the file should be cleaned up.
        """
        if ttl_days is None:
            ttl_days = get_settings().upload_ttl_days
        return datetime.now(UTC) + timedelta(days=ttl_days)


# Module-level singleton (initialized via lifespan)
storage_client = StorageClient()
