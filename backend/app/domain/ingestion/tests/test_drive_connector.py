"""Tests for Google Drive connector."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.ingestion.drive_connector import (
    GoogleDriveConnector,
    SUPPORTED_MIME_TYPES,
)
from app.domain.ingestion.exceptions import DriveAuthError


class TestSourceName:
    """Test connector identity."""

    def test_source_name(self) -> None:
        connector = GoogleDriveConnector()
        assert connector.source_name == "google_drive"


class TestAuthenticate:
    """Test OAuth2 authentication."""

    @pytest.mark.asyncio
    async def test_auth_no_credentials(self) -> None:
        """Should return False when Google credentials not configured."""
        connector = GoogleDriveConnector()
        with patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                google_client_id="",
                google_client_secret="",
                google_refresh_token="",
            )
            result = await connector.authenticate()
            assert result is False

    @pytest.mark.asyncio
    async def test_auth_no_refresh_token(self) -> None:
        """Should return False when no refresh token."""
        connector = GoogleDriveConnector()
        with patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                google_client_id="client-id",
                google_client_secret="client-secret",
                google_refresh_token="",
            )
            result = await connector.authenticate()
            assert result is False

    @pytest.mark.asyncio
    async def test_auth_success(self) -> None:
        """Should authenticate and build Drive service."""
        connector = GoogleDriveConnector()
        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "123"}]
        }

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch("app.domain.ingestion.drive_connector.build", return_value=mock_service),
            patch("app.domain.ingestion.drive_connector.Credentials"),
        ):
            mock_settings.return_value = MagicMock(
                google_client_id="client-id",
                google_client_secret="client-secret",
                google_refresh_token="refresh-token",
            )
            result = await connector.authenticate()
            assert result is True
            assert connector._service is not None


class TestListFiles:
    """Test file listing."""

    @pytest.mark.asyncio
    async def test_list_not_authenticated(self) -> None:
        """Should raise error when not authenticated."""
        connector = GoogleDriveConnector()
        with pytest.raises(DriveAuthError):
            await connector.list_files()

    @pytest.mark.asyncio
    async def test_list_files_success(self) -> None:
        """Should return file list from Drive API."""
        connector = GoogleDriveConnector()
        connector._service = MagicMock()
        connector._service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "file-1",
                    "name": "doc.pdf",
                    "mimeType": "application/pdf",
                    "size": "1024",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                    "parents": ["folder-1"],
                },
                {
                    "id": "file-2",
                    "name": "report.docx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "size": "2048",
                },
            ]
        }

        files = await connector.list_files()
        assert len(files) == 2
        assert files[0].file_id == "file-1"
        assert files[0].name == "doc.pdf"
        assert files[0].size == 1024
        assert files[1].file_id == "file-2"


class TestDownloadFile:
    """Test file download."""

    @pytest.mark.asyncio
    async def test_download_not_authenticated(self) -> None:
        """Should raise error when not authenticated."""
        connector = GoogleDriveConnector()
        with pytest.raises(DriveAuthError):
            await connector.download_file("file-1")

    @pytest.mark.asyncio
    async def test_download_pdf(self) -> None:
        """Should download a regular PDF file."""
        connector = GoogleDriveConnector()
        connector._service = MagicMock()

        # Mock get metadata
        connector._service.files.return_value.get.return_value.execute.return_value = {
            "id": "file-1",
            "name": "doc.pdf",
            "mimeType": "application/pdf",
        }

        # Mock download
        mock_request = MagicMock()
        connector._service.files.return_value.get_media.return_value = mock_request

        with patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl:
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            content, filename = await connector.download_file("file-1")
            assert filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_download_google_doc_exports_docx(self) -> None:
        """Google Docs should be exported as DOCX."""
        connector = GoogleDriveConnector()
        connector._service = MagicMock()

        connector._service.files.return_value.get.return_value.execute.return_value = {
            "id": "file-2",
            "name": "My Document",
            "mimeType": "application/vnd.google-apps.document",
        }

        mock_request = MagicMock()
        connector._service.files.return_value.export_media.return_value = mock_request

        with patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl:
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            content, filename = await connector.download_file("file-2")
            assert filename == "My Document.docx"


class TestSupportedMimeTypes:
    """Test MIME type configuration."""

    def test_pdf_supported(self) -> None:
        assert "application/pdf" in SUPPORTED_MIME_TYPES

    def test_docx_supported(self) -> None:
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in SUPPORTED_MIME_TYPES
        )

    def test_google_docs_supported(self) -> None:
        assert "application/vnd.google-apps.document" in SUPPORTED_MIME_TYPES
