"""Ingestion domain interfaces.

ABCs for source connectors. New sources (Notion, Confluence, etc.)
implement SourceConnector to integrate with the ingestion swarm.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.ingestion.schemas import DriveFileInfo, DriveFolderEntry


class SourceConnector(ABC):
    """Base contract for all source connectors.

    Each external source (Google Drive, Notion, etc.) implements this interface
    to provide file discovery and download capabilities.

    ## How to add a new source connector:
    1. Create `your_source_connector.py`
    2. Subclass `SourceConnector`
    3. Implement all abstract methods
    4. Register in `registry.py`
    5. Write tests in `tests/`
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the unique name of this source (e.g., 'google_drive')."""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable label for the UI (e.g., 'Google Drive')."""
        ...

    @classmethod
    @abstractmethod
    def is_configured(cls) -> bool:
        """Check whether the required credentials/config are present."""
        ...

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the external source.

        Returns:
            True if authentication succeeded
        """
        ...

    @abstractmethod
    async def list_files(
        self,
        folder_id: str | None = None,
        supported_types: list[str] | None = None,
    ) -> list[DriveFileInfo]:
        """List files available for ingestion.

        Args:
            folder_id: Optional folder/directory to scan. None = root.
            supported_types: Filter by MIME types. None = all.

        Returns:
            List of file info objects
        """
        ...

    @abstractmethod
    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Download a file by its ID.

        Args:
            file_id: The source-specific file identifier

        Returns:
            Tuple of (file content bytes, filename)
        """
        ...

    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get metadata for a specific file.

        Args:
            file_id: The source-specific file identifier

        Returns:
            Dict of metadata key-value pairs
        """
        ...

    @abstractmethod
    async def list_folder_children(
        self,
        folder_id: str,
    ) -> list[DriveFolderEntry]:
        """List all direct children (files AND subfolders) of a folder.

        Unlike ``list_files`` (which only returns ingestible documents),
        this returns every child including sub-folders so the orchestrator
        agent can decide which folders to recurse into.

        Args:
            folder_id: The source-specific folder identifier

        Returns:
            List of DriveFolderEntry objects (files + folders)
        """
        ...
