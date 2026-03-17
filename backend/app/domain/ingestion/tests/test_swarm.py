"""Tests for ingestion swarm orchestrator."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import DriveFileInfo
from app.domain.ingestion.swarm import IngestionSwarm


def _make_job(**kwargs) -> IngestionJob:
    """Create a test IngestionJob."""
    defaults = {
        "id": uuid.uuid4(),
        "triggered_by": uuid.uuid4(),
        "source": "google_drive",
        "status": IngestionStatus.PENDING,
        "folder_id": None,
        "total_files": 0,
        "processed_files": 0,
        "failed_files": 0,
        "skipped_files": 0,
        "error_message": None,
        "metadata_": {},
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
    }
    defaults.update(kwargs)
    job = MagicMock(spec=IngestionJob)
    for k, v in defaults.items():
        setattr(job, k, v)
    return job


def _make_file_info(**kwargs) -> DriveFileInfo:
    """Create a test DriveFileInfo."""
    defaults = {
        "file_id": f"file-{uuid.uuid4().hex[:8]}",
        "name": "test.pdf",
        "mime_type": "application/pdf",
        "size": 1024,
        "modified_time": "2025-01-01T00:00:00Z",
        "parent_folder": "folder-1",
    }
    defaults.update(kwargs)
    return DriveFileInfo(**defaults)


class TestSwarmRun:
    """Test swarm execution."""

    @pytest.mark.asyncio
    async def test_auth_failure(self) -> None:
        """Should fail job if authentication fails."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = False

        job = _make_job()
        swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)

        result = await swarm.run(job, admin_user_id=uuid.uuid4())
        assert result.status == IngestionStatus.FAILED
        assert "Authentication failed" in result.error_message

    @pytest.mark.asyncio
    async def test_no_files_found(self) -> None:
        """Should complete if no files found."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_files.return_value = []

        job = _make_job()
        swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)

        result = await swarm.run(job, admin_user_id=uuid.uuid4())
        assert result.status == IngestionStatus.COMPLETED
        assert result.total_files == 0

    @pytest.mark.asyncio
    async def test_processes_files(self) -> None:
        """Should process files from connector."""
        mock_db = AsyncMock()
        # Make db.add a regular (non-async) mock
        mock_db.add = MagicMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_files.return_value = [
            _make_file_info(name="doc.pdf", mime_type="application/pdf"),
        ]
        mock_connector.download_file.return_value = (b"fake pdf content", "doc.pdf")

        job = _make_job()

        # Mock the processor
        mock_processing_result = MagicMock()
        mock_processing_result.chunks = [
            MagicMock(chunk_index=0, content="chunk text", page_number=1, metadata={}),
        ]
        mock_processing_result.metadata = {"page_count": 1}
        mock_processing_result.page_count = 1

        with patch("app.domain.ingestion.swarm.get_processor") as mock_get_proc:
            mock_processor = AsyncMock()
            mock_processor.process.return_value = mock_processing_result
            mock_get_proc.return_value = mock_processor

            swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)

            # Mock _filter_new_files to return all files
            swarm._filter_new_files = AsyncMock(return_value=mock_connector.list_files.return_value)

            result = await swarm.run(job, admin_user_id=uuid.uuid4(), force=True)

        assert result.processed_files == 1
        assert result.status == IngestionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_handles_processing_error(self) -> None:
        """Should count failed files on processing errors."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_files.return_value = [
            _make_file_info(name="bad.pdf"),
        ]
        mock_connector.download_file.side_effect = Exception("Download failed")

        job = _make_job()

        with patch("app.domain.ingestion.swarm.get_processor") as mock_get_proc:
            mock_get_proc.return_value = AsyncMock()

            swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)
            swarm._filter_new_files = AsyncMock(return_value=mock_connector.list_files.return_value)

            result = await swarm.run(job, admin_user_id=uuid.uuid4(), force=True)

        assert result.failed_files == 1
        assert result.status == IngestionStatus.COMPLETED


class TestSwarmFilterFiles:
    """Test file deduplication filtering."""

    @pytest.mark.asyncio
    async def test_filters_existing_files(self) -> None:
        """Should filter out already-ingested files (unchanged)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        # New query returns (doc_id, file_id, modified_time) tuples
        mock_result.all.return_value = [
            (uuid.uuid4(), "existing-file-id", "2025-01-01T00:00:00Z"),
        ]
        mock_db.execute.return_value = mock_result

        mock_storage = AsyncMock()
        mock_connector = AsyncMock()

        files = [
            _make_file_info(file_id="existing-file-id", name="old.pdf"),
            _make_file_info(file_id="new-file-id", name="new.pdf"),
        ]

        swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)
        result = await swarm._filter_new_files(files)

        assert len(result) == 1
        assert result[0].file_id == "new-file-id"

    @pytest.mark.asyncio
    async def test_detects_updated_files(self) -> None:
        """Should include files that have been modified on Drive."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        existing_doc_id = uuid.uuid4()
        mock_result.all.return_value = [
            (existing_doc_id, "updated-file-id", "2025-01-01T00:00:00Z"),
        ]
        mock_db.execute.return_value = mock_result
        # Mock get() to return a document for marking as stale
        mock_doc = MagicMock()
        mock_doc.metadata_ = {}
        mock_db.get.return_value = mock_doc

        mock_storage = AsyncMock()
        mock_connector = AsyncMock()

        files = [
            _make_file_info(
                file_id="updated-file-id",
                name="updated.pdf",
                modified_time="2025-06-01T00:00:00Z",  # Newer than stored
            ),
        ]

        swarm = IngestionSwarm(db=mock_db, storage=mock_storage, connector=mock_connector)
        result = await swarm._filter_new_files(files)

        assert len(result) == 1
        assert result[0].file_id == "updated-file-id"
        # Old doc should be marked stale
        assert mock_doc.metadata_.get("_stale") is True
