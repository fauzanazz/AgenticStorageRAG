"""Tests for ingestion domain exceptions."""

from app.domain.ingestion.exceptions import (
    DriveAccessError,
    DriveAuthError,
    DriveFileDownloadError,
    IngestionAlreadyRunningError,
    IngestionError,
    IngestionJobNotFoundError,
    UnsupportedDriveFileError,
)


class TestExceptions:
    """Test exception creation and messages."""

    def test_base_error(self) -> None:
        err = IngestionError("test")
        assert str(err) == "test"
        assert err.message == "test"

    def test_drive_auth_error(self) -> None:
        err = DriveAuthError("bad creds")
        assert "bad creds" in str(err)

    def test_drive_access_error(self) -> None:
        err = DriveAccessError("folder-123")
        assert "folder-123" in str(err)

    def test_drive_download_error(self) -> None:
        err = DriveFileDownloadError("file-456", "timeout")
        assert "file-456" in str(err)
        assert "timeout" in str(err)

    def test_job_not_found(self) -> None:
        err = IngestionJobNotFoundError("abc-def")
        assert "abc-def" in str(err)

    def test_already_running(self) -> None:
        err = IngestionAlreadyRunningError()
        assert "already running" in str(err).lower()

    def test_unsupported_file(self) -> None:
        err = UnsupportedDriveFileError("doc.pptx", "application/pptx")
        assert "doc.pptx" in str(err)
        assert "application/pptx" in str(err)
