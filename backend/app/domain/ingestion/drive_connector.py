"""Google Drive source connector.

Read-only connector for ingesting files from Google Drive.
Supports two authentication methods:

1. **Service Account** (production): Set GOOGLE_SERVICE_ACCOUNT_FILE or
   GOOGLE_SERVICE_ACCOUNT_JSON. The Drive folder must be shared with the SA email.

2. **OAuth2** (personal account): Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
   and GOOGLE_REFRESH_TOKEN. Run `uv run python -m app.scripts.google_auth`
   to obtain the refresh token. Accesses YOUR Drive directly -- no sharing needed.

Service Account is tried first; OAuth2 is the fallback.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any

from google.oauth2 import service_account
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
from app.domain.ingestion.schemas import DriveFolderEntry, DriveFileInfo

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
    """Google Drive source connector with dual auth support.

    Priority order:
    1. Service Account (GOOGLE_SERVICE_ACCOUNT_FILE / _JSON)
    2. OAuth2 refresh token (GOOGLE_CLIENT_ID + SECRET + REFRESH_TOKEN)

    Service Account is ideal for production (no token expiry, headless).
    OAuth2 is ideal for personal use (accesses your own Drive, no sharing needed).
    """

    def __init__(self) -> None:
        self._service: Any | None = None
        self._credentials: Any | None = None
        self._auth_method: str | None = None

    @property
    def source_name(self) -> str:
        return "google_drive"

    async def authenticate(self) -> bool:
        """Authenticate with Google Drive.

        Tries Service Account first, then falls back to OAuth2.

        Returns:
            True if authentication succeeded
        """
        settings = get_settings()

        try:
            # --- Option 1: Service Account (preferred) ---
            if settings.google_service_account_file:
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        settings.google_service_account_file,
                        scopes=SCOPES,
                    )
                )
                self._auth_method = "service_account_file"

            elif settings.google_service_account_json:
                info = json.loads(settings.google_service_account_json)
                self._credentials = (
                    service_account.Credentials.from_service_account_info(
                        info,
                        scopes=SCOPES,
                    )
                )
                self._auth_method = "service_account_json"

            # --- Option 2: OAuth2 refresh token (personal account) ---
            elif (
                settings.google_client_id
                and settings.google_client_secret
                and settings.google_refresh_token
            ):
                self._credentials = Credentials(
                    token=None,  # Will be refreshed automatically
                    refresh_token=settings.google_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    scopes=SCOPES,
                )
                self._auth_method = "oauth2"

            else:
                logger.error(
                    "Google Drive not configured. Set either:\n"
                    "  - GOOGLE_SERVICE_ACCOUNT_FILE (or _JSON) for Service Account, or\n"
                    "  - GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET + GOOGLE_REFRESH_TOKEN for OAuth2.\n"
                    "  Run `uv run python -m app.scripts.google_auth` to get a refresh token."
                )
                return False

            # Build the Drive API service
            self._service = build(
                "drive", "v3", credentials=self._credentials
            )

            # Test with a simple request
            test_request = self._service.files().list(pageSize=1, fields="files(id)")
            await asyncio.to_thread(test_request.execute)

            logger.info(
                "Google Drive authentication successful (%s)", self._auth_method
            )
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
                result = await asyncio.to_thread(request.execute)

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
            meta_request = self._service.files().get(fileId=file_id, fields=FILE_FIELDS)
            meta = await asyncio.to_thread(meta_request.execute)
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
                _, done = await asyncio.to_thread(downloader.next_chunk)

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
            meta_request = self._service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, createdTime, "
                       "owners, lastModifyingUser, webViewLink",
            )
            meta = await asyncio.to_thread(meta_request.execute)
            return dict(meta)
        except HttpError as e:
            raise DriveAccessError(file_id) from e

    async def list_folder_children(
        self,
        folder_id: str,
    ) -> list[DriveFolderEntry]:
        """List ALL direct children (files + subfolders) of a Drive folder.

        Unlike ``list_files``, this does NOT filter by MIME type -- it
        returns every child so the orchestrator agent can see subfolders
        and decide which ones to recurse into.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            List of DriveFolderEntry (files + folders)
        """
        if not self._service:
            raise DriveAuthError("Not authenticated. Call authenticate() first.")

        entries: list[DriveFolderEntry] = []
        page_token: str | None = None

        try:
            while True:
                request = self._service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields=f"nextPageToken, files({FILE_FIELDS})",
                    pageSize=100,
                    pageToken=page_token,
                    orderBy="folder,name",
                )
                result = await asyncio.to_thread(request.execute)

                for f in result.get("files", []):
                    mime = f["mimeType"]
                    entries.append(
                        DriveFolderEntry(
                            file_id=f["id"],
                            name=f["name"],
                            mime_type=mime,
                            size=int(f["size"]) if f.get("size") else None,
                            modified_time=f.get("modifiedTime"),
                            is_folder=(mime == "application/vnd.google-apps.folder"),
                        )
                    )

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            logger.info(
                "Folder %s: %d children (%d folders, %d files)",
                folder_id,
                len(entries),
                sum(1 for e in entries if e.is_folder),
                sum(1 for e in entries if not e.is_folder),
            )
            return entries

        except HttpError as e:
            logger.error("Drive API error listing folder children: %s", e)
            raise DriveAccessError(folder_id) from e
