"""Tests for Google Drive connector (dual auth: Service Account + OAuth2)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.domain.ingestion.drive_connector import (
    SUPPORTED_MIME_TYPES,
    GoogleDriveConnector,
)
from app.domain.ingestion.exceptions import DriveAuthError


# Shared mock settings factory -- all auth fields empty by default
def _empty_settings(**overrides: str) -> MagicMock:
    defaults = {
        "google_service_account_file": "",
        "google_service_account_json": "",
        "google_client_id": "",
        "google_client_secret": "",
        "google_refresh_token": "",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _mock_drive_service() -> MagicMock:
    svc = MagicMock()
    svc.files.return_value.list.return_value.execute.return_value = {"files": [{"id": "123"}]}
    return svc


class TestSourceName:
    """Test connector identity."""

    def test_source_name(self) -> None:
        connector = GoogleDriveConnector()
        assert connector.source_name == "google_drive"


class TestAuthenticate:
    """Test dual auth: Service Account and OAuth2."""

    # --- No credentials at all ---

    @pytest.mark.asyncio
    async def test_auth_no_credentials(self) -> None:
        """Should return False when nothing is configured."""
        connector = GoogleDriveConnector()
        with patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings:
            mock_settings.return_value = _empty_settings()
            result = await connector.authenticate()
            assert result is False

    # --- Service Account: file path ---

    @pytest.mark.asyncio
    async def test_auth_sa_file(self) -> None:
        """Should authenticate using a Service Account JSON key file."""
        connector = GoogleDriveConnector()
        mock_creds = MagicMock()

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch("app.domain.ingestion.drive_connector.build", return_value=_mock_drive_service()),
            patch(
                "app.domain.ingestion.drive_connector.service_account.Credentials.from_service_account_file",
                return_value=mock_creds,
            ) as mock_from_file,
        ):
            mock_settings.return_value = _empty_settings(
                google_service_account_file="/path/to/sa.json"
            )
            result = await connector.authenticate()
            assert result is True
            assert connector._auth_method == "service_account_file"
            mock_from_file.assert_called_once()

    # --- Service Account: inline JSON ---

    @pytest.mark.asyncio
    async def test_auth_sa_inline_json(self) -> None:
        """Should authenticate using inline Service Account JSON."""
        connector = GoogleDriveConnector()
        mock_creds = MagicMock()
        sa_json = json.dumps({"type": "service_account", "project_id": "test"})

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch("app.domain.ingestion.drive_connector.build", return_value=_mock_drive_service()),
            patch(
                "app.domain.ingestion.drive_connector.service_account.Credentials.from_service_account_info",
                return_value=mock_creds,
            ) as mock_from_info,
        ):
            mock_settings.return_value = _empty_settings(google_service_account_json=sa_json)
            result = await connector.authenticate()
            assert result is True
            assert connector._auth_method == "service_account_json"
            mock_from_info.assert_called_once()

    # --- Service Account takes precedence over OAuth2 ---

    @pytest.mark.asyncio
    async def test_auth_sa_takes_precedence_over_oauth(self) -> None:
        """SA file should be used even when OAuth2 vars are also set."""
        connector = GoogleDriveConnector()
        mock_creds = MagicMock()

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch("app.domain.ingestion.drive_connector.build", return_value=_mock_drive_service()),
            patch(
                "app.domain.ingestion.drive_connector.service_account.Credentials.from_service_account_file",
                return_value=mock_creds,
            ) as mock_from_file,
            patch(
                "app.domain.ingestion.drive_connector.Credentials",
            ) as mock_oauth_creds,
        ):
            mock_settings.return_value = _empty_settings(
                google_service_account_file="/path/to/sa.json",
                google_client_id="client-id",
                google_client_secret="client-secret",
                google_refresh_token="refresh-token",
            )
            result = await connector.authenticate()
            assert result is True
            assert connector._auth_method == "service_account_file"
            mock_from_file.assert_called_once()
            mock_oauth_creds.assert_not_called()

    # --- OAuth2 refresh token ---

    @pytest.mark.asyncio
    async def test_auth_oauth2(self) -> None:
        """Should authenticate using OAuth2 refresh token."""
        connector = GoogleDriveConnector()

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch("app.domain.ingestion.drive_connector.build", return_value=_mock_drive_service()),
            patch("app.domain.ingestion.drive_connector.Credentials") as mock_creds_cls,
        ):
            mock_creds_cls.return_value = MagicMock()
            mock_settings.return_value = _empty_settings(
                google_client_id="client-id",
                google_client_secret="client-secret",
                google_refresh_token="refresh-token",
            )
            result = await connector.authenticate()
            assert result is True
            assert connector._auth_method == "oauth2"
            mock_creds_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_oauth2_partial_creds_returns_false(self) -> None:
        """Should return False if only some OAuth2 fields are set."""
        connector = GoogleDriveConnector()
        with patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings:
            # Missing refresh token
            mock_settings.return_value = _empty_settings(
                google_client_id="client-id",
                google_client_secret="client-secret",
            )
            result = await connector.authenticate()
            assert result is False

    # --- Auth failure ---

    @pytest.mark.asyncio
    async def test_auth_failure_raises_drive_auth_error(self) -> None:
        """Should raise DriveAuthError when authentication fails."""
        connector = GoogleDriveConnector()

        with (
            patch("app.domain.ingestion.drive_connector.get_settings") as mock_settings,
            patch(
                "app.domain.ingestion.drive_connector.service_account.Credentials.from_service_account_file",
                side_effect=Exception("Invalid key file"),
            ),
        ):
            mock_settings.return_value = _empty_settings(
                google_service_account_file="/bad/path.json"
            )
            with pytest.raises(DriveAuthError):
                await connector.authenticate()


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
        connector._credentials = MagicMock()  # mark as authenticated

        mock_svc = MagicMock()
        mock_svc.files.return_value.list.return_value.execute.return_value = {
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

        with patch.object(connector, "_build_service", return_value=mock_svc):
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
        connector._credentials = MagicMock()  # mark as authenticated

        mock_svc = MagicMock()
        mock_svc.files.return_value.get.return_value.execute.return_value = {
            "id": "file-1",
            "name": "doc.pdf",
            "mimeType": "application/pdf",
        }
        mock_request = MagicMock()
        mock_svc.files.return_value.get_media.return_value = mock_request

        with (
            patch.object(connector, "_build_service", return_value=mock_svc),
            patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl,
        ):
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            _content, filename = await connector.download_file("file-1")
            assert filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_download_google_doc_exports_docx(self) -> None:
        """Google Docs should be exported as DOCX."""
        connector = GoogleDriveConnector()
        connector._credentials = MagicMock()  # mark as authenticated

        mock_svc = MagicMock()
        mock_svc.files.return_value.get.return_value.execute.return_value = {
            "id": "file-2",
            "name": "My Document",
            "mimeType": "application/vnd.google-apps.document",
        }
        mock_request = MagicMock()
        mock_svc.files.return_value.export_media.return_value = mock_request

        with (
            patch.object(connector, "_build_service", return_value=mock_svc),
            patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl,
        ):
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            _content, filename = await connector.download_file("file-2")
            assert filename == "My Document.docx"

    @pytest.mark.asyncio
    async def test_download_google_spreadsheet_exports_pdf(self) -> None:
        """Google Spreadsheets should be exported as PDF."""
        connector = GoogleDriveConnector()
        connector._credentials = MagicMock()

        mock_svc = MagicMock()
        mock_svc.files.return_value.get.return_value.execute.return_value = {
            "id": "file-3",
            "name": "My Spreadsheet",
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        mock_request = MagicMock()
        mock_svc.files.return_value.export_media.return_value = mock_request

        with (
            patch.object(connector, "_build_service", return_value=mock_svc),
            patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl,
        ):
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            _content, filename = await connector.download_file("file-3")
            assert filename == "My Spreadsheet.pdf"
            mock_svc.files.return_value.export_media.assert_called_once_with(
                fileId="file-3", mimeType="application/pdf"
            )

    @pytest.mark.asyncio
    async def test_download_google_presentation_exports_pdf(self) -> None:
        """Google Presentations should be exported as PDF."""
        connector = GoogleDriveConnector()
        connector._credentials = MagicMock()

        mock_svc = MagicMock()
        mock_svc.files.return_value.get.return_value.execute.return_value = {
            "id": "file-4",
            "name": "My Slides",
            "mimeType": "application/vnd.google-apps.presentation",
        }
        mock_request = MagicMock()
        mock_svc.files.return_value.export_media.return_value = mock_request

        with (
            patch.object(connector, "_build_service", return_value=mock_svc),
            patch("app.domain.ingestion.drive_connector.MediaIoBaseDownload") as mock_dl,
        ):
            mock_dl_instance = MagicMock()
            mock_dl_instance.next_chunk.return_value = (None, True)
            mock_dl.return_value = mock_dl_instance

            _content, filename = await connector.download_file("file-4")
            assert filename == "My Slides.pdf"
            mock_svc.files.return_value.export_media.assert_called_once_with(
                fileId="file-4", mimeType="application/pdf"
            )


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

    def test_google_spreadsheets_supported(self) -> None:
        assert "application/vnd.google-apps.spreadsheet" in SUPPORTED_MIME_TYPES

    def test_google_presentations_supported(self) -> None:
        assert "application/vnd.google-apps.presentation" in SUPPORTED_MIME_TYPES
