"""Ingestion domain exceptions.

Typed errors for the ingestion pipeline.
"""

from __future__ import annotations


class IngestionError(Exception):
    """Base exception for all ingestion errors."""

    def __init__(self, message: str = "Ingestion error") -> None:
        self.message = message
        super().__init__(self.message)


class DriveAuthError(IngestionError):
    """Google Drive authentication/authorization failure."""

    def __init__(self, detail: str = "Drive authentication failed") -> None:
        super().__init__(f"Google Drive auth error: {detail}")


class DriveAccessError(IngestionError):
    """Cannot access the requested Drive resource."""

    def __init__(self, resource: str = "unknown") -> None:
        super().__init__(f"Cannot access Drive resource: {resource}")


class DriveFileDownloadError(IngestionError):
    """Failed to download a file from Drive."""

    def __init__(self, file_id: str, detail: str = "") -> None:
        super().__init__(f"Failed to download Drive file {file_id}: {detail}")


class IngestionJobNotFoundError(IngestionError):
    """Ingestion job not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Ingestion job not found: {job_id}")


class IngestionAlreadyRunningError(IngestionError):
    """An ingestion job is already running."""

    def __init__(self) -> None:
        super().__init__("An ingestion job is already running. Wait for it to complete.")


class UnsupportedDriveFileError(IngestionError):
    """File type from Drive is not supported for ingestion."""

    def __init__(self, file_name: str, mime_type: str) -> None:
        super().__init__(f"Unsupported Drive file: {file_name} ({mime_type})")
