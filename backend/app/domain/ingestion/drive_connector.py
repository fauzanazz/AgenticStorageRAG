"""Google Drive source connector.

Read-only OAuth2 connector for ingesting files from the owner's Google Drive.
Uses the stored refresh token for headless operation after initial consent.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.domain.ingestion.exceptions import (
    DriveAccessError,
    DriveAuthError,
    DriveFileDownloadError,
)
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.schemas import DriveFileInfo

logger = logging.getLogger(__name__)

# MIME types we can ingest (maps to our document processors)
SUPPORTED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    # Google Docs are exported as DOCX
    "application/vnd.google-apps.document": "docx",
}

# Google Drive API scopes -- read-only
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Fields to request from Drive API
FILE_FIELDS = "id, name, mimeType, size, modifiedTime, parents"
LIST_FIELDS = f"nextPageToken, files({FILE_FIELDS})"


class GoogleDriveConnector(SourceConnector):
    """Google Drive source connector using OAuth2 refresh token.

    Authentication flow:
    1. Owner completes OAuth2 consent once (via /admin/ingestion/auth)
    2. Refresh token stored in config/env
    3. Connector uses refresh token headlessly for all subsequent requests

    This connector is read-only and owner-only. End users cannot connect
    their own Drive accounts.
    """

    def __init__(self) -> None:
        self._service: Any | None = None
        self._credentials: Credentials | None = None

    @property
    def source_name(self) -> str:
        return "google_drive"

    async def authenticate(self) -> bool:
        """Authenticate using the stored OAuth2 refresh token.

        Returns:
            True if authentication succeeded
        """
        settings = get_settings()

        if not settings.google_client_id or not settings.google_client_secret:
            logger.error("Google OAuth2 credentials not configured")
            return False

        if not settings.google_refresh_token:
            logger.warning(
                "No Google refresh token. Complete OAuth2 consent first "
                "via /admin/ingestion/auth/initiate"
            )
            return False

        try:
            self._credentials = Credentials(
                token=None,  # Will be refreshed automatically
                refresh_token=settings.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=SCOPES,
            )

            # Build the Drive API service
            self._service = build(
                "drive", "v3", credentials=self._credentials
            )

            # Test with a simple request
            self._service.files().list(
                pageSize=1, fields="files(id)"
            ).execute()

            logger.info("Google Drive authentication successful")
            return True

        except Exception as e:
            logger.error("Google Drive authentication failed: %s", e)
            raise DriveAuthError(str(e)) from e

    async def list_files(
        self,
        folder_id: str | None = None,
        supported_types: list[str] | None = None,
    ) -> list[DriveFileInfo]:
        """List files in a Drive folder (or root).

        Args:
            folder_id: Drive folder ID. None = search all accessible files.
            supported_types: Filter by MIME types. None = use default supported types.

        Returns:
            List of DriveFileInfo for ingestible files
        """
        if not self._service:
            raise DriveAuthError("Not authenticated. Call authenticate() first.")

        allowed_types = supported_types or list(SUPPORTED_MIME_TYPES.keys())
        files: list[DriveFileInfo] = []
        page_token: str | None = None

        # Build query
        type_conditions = " or ".join(
            f"mimeType='{mt}'" for mt in allowed_types
        )
        query = f"({type_conditions}) and trashed=false"

        if folder_id:
            query = f"'{folder_id}' in parents and {query}"

        try:
            while True:
                request = self._service.files().list(
                    q=query,
                    fields=LIST_FIELDS,
                    pageSize=100,
                    pageToken=page_token,
                )
                result = request.execute()

                for f in result.get("files", []):
                    files.append(
                        DriveFileInfo(
                            file_id=f["id"],
                            name=f["name"],
                            mime_type=f["mimeType"],
                            size=int(f["size"]) if f.get("size") else None,
                            modified_time=f.get("modifiedTime"),
                            parent_folder=(
                                f["parents"][0]
                                if f.get("parents")
                                else None
                            ),
                        )
                    )

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            logger.info("Found %d ingestible files in Drive", len(files))
            return files

        except HttpError as e:
            logger.error("Drive API error listing files: %s", e)
            raise DriveAccessError(folder_id or "root") from e

    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Download a file from Drive.

        For Google Docs, exports as DOCX. For other files, downloads directly.

        Args:
            file_id: Google Drive file ID

        Returns:
            Tuple of (file bytes, original filename)
        """
        if not self._service:
            raise DriveAuthError("Not authenticated. Call authenticate() first.")

        try:
            # Get file metadata first
            meta = self._service.files().get(
                fileId=file_id, fields=FILE_FIELDS
            ).execute()
            filename = meta["name"]
            mime_type = meta["mimeType"]

            # Google Docs need to be exported
            if mime_type == "application/vnd.google-apps.document":
                export_mime = (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                )
                request = self._service.files().export_media(
                    fileId=file_id, mimeType=export_mime
                )
                if not filename.endswith(".docx"):
                    filename = f"{filename}.docx"
            else:
                request = self._service.files().get_media(fileId=file_id)

            # Download to buffer
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            content = buffer.getvalue()
            logger.info("Downloaded %s (%d bytes)", filename, len(content))
            return content, filename

        except HttpError as e:
            raise DriveFileDownloadError(file_id, str(e)) from e

    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get metadata for a Drive file."""
        if not self._service:
            raise DriveAuthError("Not authenticated. Call authenticate() first.")

        try:
            meta = self._service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, createdTime, "
                       "owners, lastModifyingUser, webViewLink",
            ).execute()
            return dict(meta)
        except HttpError as e:
            raise DriveAccessError(file_id) from e
