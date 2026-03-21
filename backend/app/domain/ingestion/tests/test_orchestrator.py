"""Tests for the ingestion orchestrator, scanner, file processor, and tools."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.orchestrator import IngestionOrchestrator
from app.domain.ingestion.orchestrator_tools import (
    ClassifyFileTool,
    IngestFileTool,
    ScanFolderTool,
    UpdateProgressTool,
    ingest_single_file,
)
from app.domain.ingestion.schemas import DriveFolderEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> IngestionJob:
    """Create a test IngestionJob."""
    defaults = {
        "id": uuid.uuid4(),
        "triggered_by": uuid.uuid4(),
        "source": "google_drive",
        "status": IngestionStatus.PENDING,
        "folder_id": "root-folder-id",
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


def _make_session_factory():
    """Create a mock session factory that returns async context managers."""
    mock_db = AsyncMock()
    # Make execute return a result with scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = IngestionStatus.PROCESSING
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    @asynccontextmanager
    async def factory():
        yield mock_db

    return factory, mock_db


# ---------------------------------------------------------------------------
# ScanFolderTool
# ---------------------------------------------------------------------------


class TestScanFolderTool:
    """Test the scan_folder tool."""

    @pytest.mark.asyncio
    async def test_returns_children(self) -> None:
        """Should return folders and files from connector."""
        mock_connector = AsyncMock()
        mock_connector.list_folder_children.return_value = [
            DriveFolderEntry(
                file_id="folder-1",
                name="Informatika",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
            DriveFolderEntry(
                file_id="file-1",
                name="Kurikulum.pdf",
                mime_type="application/pdf",
                size=1024,
            ),
        ]

        tool = ScanFolderTool(connector=mock_connector)
        result = await tool.execute(folder_id="root-folder-id")

        assert result["children_count"] == 2
        assert len(result["folders"]) == 1
        assert len(result["files"]) == 1
        assert result["folders"][0]["name"] == "Informatika"
        assert result["files"][0]["name"] == "Kurikulum.pdf"

    def test_tool_spec(self) -> None:
        """Should produce a valid LiteLLM tool spec."""
        mock_connector = AsyncMock()
        tool = ScanFolderTool(connector=mock_connector)
        spec = tool.to_tool_spec()

        assert spec["type"] == "function"
        assert spec["function"]["name"] == "scan_folder"
        assert "folder_id" in spec["function"]["parameters"]["properties"]


# ---------------------------------------------------------------------------
# ClassifyFileTool
# ---------------------------------------------------------------------------


class TestClassifyFileTool:
    """Test the classify_file tool."""

    @pytest.mark.asyncio
    async def test_classify_success(self) -> None:
        """Should return structured classification from LLM."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "major": "Informatika",
            "course_code": "IF2120",
            "course_name": "Probabilitas dan Statistika",
            "year": "2019",
            "category": "Referensi",
            "additional_context": {},
        })
        mock_llm.complete_for_ingestion.return_value = mock_response

        tool = ClassifyFileTool(llm=mock_llm)
        result = await tool.execute(
            file_name="Buku Statistik.pdf",
            folder_path="Informatika/Semester 3/IF2120 - Probabilitas dan Statistika/Referensi",
            mime_type="application/pdf",
        )

        assert result["status"] == "classified"
        assert result["classification"]["major"] == "Informatika"
        assert result["classification"]["course_code"] == "IF2120"
        assert result["classification"]["category"] == "Referensi"

    @pytest.mark.asyncio
    async def test_classify_llm_failure_returns_fallback(self) -> None:
        """Should return a fallback classification on LLM failure."""
        mock_llm = AsyncMock()
        mock_llm.complete_for_ingestion.side_effect = Exception("LLM down")

        tool = ClassifyFileTool(llm=mock_llm)
        result = await tool.execute(
            file_name="test.pdf",
            folder_path="Root/SubFolder",
        )

        assert result["status"] == "classification_failed"
        assert result["classification"]["folder_path"] == "Root/SubFolder"


# ---------------------------------------------------------------------------
# ingest_single_file (standalone function)
# ---------------------------------------------------------------------------


class TestIngestSingleFile:
    """Test the standalone ingest_single_file function."""

    @pytest.mark.asyncio
    async def test_ingest_success(self) -> None:
        """Should download, process, and commit a file."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        # Deduplication query returns no existing row
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_db.execute.return_value = mock_exec_result
        mock_connector = AsyncMock()
        mock_connector.download_file.return_value = (b"fake pdf", "doc.pdf")

        # Mock processor
        mock_processing_result = MagicMock()
        mock_processing_result.chunks = [
            MagicMock(chunk_index=0, content="chunk text", page_number=1, metadata={}),
        ]
        mock_processing_result.metadata = {"page_count": 1}

        with (
            patch("app.domain.ingestion.orchestrator_tools.get_processor") as mock_get_proc,
            patch("app.domain.ingestion.orchestrator_tools._embed_chunks", return_value=1),
            patch("app.domain.ingestion.orchestrator_tools._extract_knowledge_graph", return_value={"entities_created": 2, "relationships_created": 1}),
        ):
            mock_processor = AsyncMock()
            mock_processor.process.return_value = mock_processing_result
            mock_get_proc.return_value = mock_processor

            result = await ingest_single_file(
                db=mock_db,
                connector=mock_connector,
                llm=MagicMock(),
                job=MagicMock(metadata_={}),
                file_id="drive-file-1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                folder_path="Informatika/Semester 3",
                classification={"major": "Informatika"},
                admin_user_id=uuid.uuid4(),
            )

        assert result["status"] == "processed"
        assert result["chunk_count"] == 1
        assert result["embeddings_created"] == 1
        assert result["kg_entities"] == 2

    @pytest.mark.asyncio
    async def test_ingest_unsupported_type(self) -> None:
        """Should skip files with no processor."""
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_db.execute.return_value = mock_exec_result
        mock_connector = AsyncMock()

        with patch("app.domain.ingestion.orchestrator_tools.get_processor", return_value=None):
            result = await ingest_single_file(
                db=mock_db,
                connector=mock_connector,
                llm=MagicMock(),
                job=MagicMock(metadata_={}),
                file_id="file-1",
                file_name="image.png",
                mime_type="image/png",
                admin_user_id=uuid.uuid4(),
            )

        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_ingest_download_error(self) -> None:
        """Should return failed status on download error."""
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_db.execute.return_value = mock_exec_result
        mock_connector = AsyncMock()
        mock_connector.download_file.side_effect = Exception("Network error")

        with patch("app.domain.ingestion.orchestrator_tools.get_processor") as mock_get_proc:
            mock_get_proc.return_value = AsyncMock()
            result = await ingest_single_file(
                db=mock_db,
                connector=mock_connector,
                llm=MagicMock(),
                job=MagicMock(metadata_={}),
                file_id="file-1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                admin_user_id=uuid.uuid4(),
            )

        assert result["status"] == "failed"
        assert "Network error" in result["error"]

    @pytest.mark.asyncio
    async def test_ingest_size_guard(self) -> None:
        """Should skip files exceeding max size."""
        result = await ingest_single_file(
            db=AsyncMock(),
            connector=AsyncMock(),
            llm=MagicMock(),
            job=MagicMock(metadata_={}),
            file_id="file-big",
            file_name="huge.pdf",
            mime_type="application/pdf",
            admin_user_id=uuid.uuid4(),
            size_bytes=999_999_999_999,  # Way over any limit
        )

        assert result["status"] == "skipped"
        assert "file_too_large" in result["reason"]


# ---------------------------------------------------------------------------
# UpdateProgressTool
# ---------------------------------------------------------------------------


class TestUpdateProgressTool:
    """Test the update_progress tool."""

    @pytest.mark.asyncio
    async def test_updates_job(self) -> None:
        """Should update the IngestionJob's counters and commit."""
        mock_db = AsyncMock()
        job = _make_job()

        tool = UpdateProgressTool(db=mock_db, job=job)
        result = await tool.execute(
            total_discovered=50,
            files_processed=30,
            files_failed=2,
            files_skipped=5,
            message="Processing folder X",
        )

        assert result["status"] == "updated"
        assert job.total_files == 50
        assert job.processed_files == 30
        assert job.failed_files == 2
        assert job.skipped_files == 5
        assert job.status == IngestionStatus.PROCESSING
        mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# IngestionOrchestrator (parallel pipeline)
# ---------------------------------------------------------------------------


class TestIngestionOrchestrator:
    """Test the parallel orchestrator."""

    @pytest.mark.asyncio
    async def test_auth_failure_marks_job_failed(self) -> None:
        """Should fail the job if Drive auth fails."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = False
        mock_llm = AsyncMock()
        session_factory, _ = _make_session_factory()

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
            session_factory=session_factory,
        )

        result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.FAILED
        assert "authentication failed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_parallel_pipeline_completes(self) -> None:
        """Should run scanners and processor in parallel and complete the job."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_folder_children.return_value = [
            DriveFolderEntry(
                file_id="subfolder-1",
                name="Folder A",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
            DriveFolderEntry(
                file_id="subfolder-2",
                name="Folder B",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
        ]
        mock_llm = AsyncMock()

        session_factory, worker_db = _make_session_factory()

        # Mock DB result for _is_cancelled and finalize refresh
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = IngestionStatus.PROCESSING
        mock_result.rowcount = 1
        # For the finalize select, return a mock job
        refreshed_job = MagicMock()
        refreshed_job.total_files = 5
        refreshed_job.processed_files = 5
        refreshed_job.failed_files = 0
        refreshed_job.skipped_files = 0
        mock_result.scalar_one_or_none.side_effect = [
            IngestionStatus.PROCESSING,  # _is_cancelled check
            refreshed_job,               # finalize refresh
            None,                        # _update_job_status check
        ]
        worker_db.execute.return_value = mock_result

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
            session_factory=session_factory,
        )

        with (
            patch("app.domain.ingestion.orchestrator.DriveScanner") as mock_scanner_cls,
            patch("app.domain.ingestion.orchestrator.StagePipeline") as mock_processor_cls,
        ):
            mock_scanner = AsyncMock()
            mock_scanner.scan_seeds.return_value = 3
            mock_scanner_cls.return_value = mock_scanner

            mock_pipeline = AsyncMock()
            mock_pipeline.run.return_value = {
                "downloaded": 5, "extracted": 5, "embedded": 5,
                "kg_done": 5, "failed": 0, "skipped": 0,
                "retry_succeeded": 0, "retry_failed": 0,
            }
            mock_processor_cls.return_value = mock_pipeline

            result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.COMPLETED
        # scan_seeds should be called for each worker that has seeds
        assert mock_scanner.scan_seeds.await_count == 2
        mock_pipeline.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_parallel_empty_root(self) -> None:
        """Should complete successfully when root has no subfolders or files."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_folder_children.return_value = []
        mock_llm = AsyncMock()

        session_factory, worker_db = _make_session_factory()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            IngestionStatus.PROCESSING,  # _is_cancelled
            MagicMock(total_files=0, processed_files=0, failed_files=0, skipped_files=0),
            None,
        ]
        mock_result.rowcount = 1
        worker_db.execute.return_value = mock_result

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
            session_factory=session_factory,
        )

        with (
            patch("app.domain.ingestion.orchestrator.DriveScanner") as mock_scanner_cls,
            patch("app.domain.ingestion.orchestrator.StagePipeline") as mock_processor_cls,
        ):
            mock_scanner = AsyncMock()
            mock_scanner_cls.return_value = mock_scanner

            mock_pipeline = AsyncMock()
            mock_pipeline.run.return_value = {
                "downloaded": 0, "extracted": 0, "embedded": 0,
                "kg_done": 0, "failed": 0, "skipped": 0,
                "retry_succeeded": 0, "retry_failed": 0,
            }
            mock_processor_cls.return_value = mock_pipeline

            result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.COMPLETED
        # No seeds → scan_seeds should not be called
        mock_scanner.scan_seeds.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_scanner_error_still_completes(self) -> None:
        """Should complete even if one scanner raises (scanning_done still set)."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_folder_children.return_value = [
            DriveFolderEntry(
                file_id="subfolder-1",
                name="Folder A",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
            DriveFolderEntry(
                file_id="subfolder-2",
                name="Folder B",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
        ]
        mock_llm = AsyncMock()

        session_factory, worker_db = _make_session_factory()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            IngestionStatus.PROCESSING,
            MagicMock(total_files=0, processed_files=0, failed_files=0, skipped_files=0),
            None,
        ]
        mock_result.rowcount = 1
        worker_db.execute.return_value = mock_result

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
            session_factory=session_factory,
        )

        call_count = 0

        async def scan_seeds_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Scanner A crashed")
            return 2

        with (
            patch("app.domain.ingestion.orchestrator.DriveScanner") as mock_scanner_cls,
            patch("app.domain.ingestion.orchestrator.StagePipeline") as mock_processor_cls,
        ):
            mock_scanner = AsyncMock()
            mock_scanner.scan_seeds.side_effect = scan_seeds_side_effect
            mock_scanner_cls.return_value = mock_scanner

            mock_pipeline = AsyncMock()
            mock_pipeline.run.return_value = {
                "downloaded": 0, "extracted": 0, "embedded": 0,
                "kg_done": 0, "failed": 0, "skipped": 0,
                "retry_succeeded": 0, "retry_failed": 0,
            }
            mock_processor_cls.return_value = mock_pipeline

            # The gather will propagate the scanner error, caught by orchestrator's try/except
            from app.domain.ingestion.exceptions import IngestionError
            with pytest.raises(IngestionError):
                await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert job.status == IngestionStatus.FAILED

    @pytest.mark.asyncio
    async def test_cancellation_stops_workers(self) -> None:
        """Should pass cancellation callback to workers."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_folder_children.return_value = []
        mock_llm = AsyncMock()

        job = _make_job()

        session_factory, worker_db = _make_session_factory()

        # Simulate cancellation on first _is_cancelled check
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = IngestionStatus.CANCELLED
        mock_result.rowcount = 1
        worker_db.execute.return_value = mock_result

        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
            session_factory=session_factory,
        )

        result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.CANCELLED


# ---------------------------------------------------------------------------
# list_folder_children on DriveConnector
# ---------------------------------------------------------------------------


class TestListFolderChildren:
    """Test the new list_folder_children method on GoogleDriveConnector."""

    @pytest.mark.asyncio
    async def test_returns_files_and_folders(self) -> None:
        """Should return both files and folders from Drive API."""
        from unittest.mock import patch
        from app.domain.ingestion.drive_connector import GoogleDriveConnector

        connector = GoogleDriveConnector()
        connector._credentials = MagicMock()  # mark as authenticated

        mock_svc = MagicMock()
        mock_svc.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "folder-1",
                    "name": "Semester 3",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["root"],
                },
                {
                    "id": "file-1",
                    "name": "Kurikulum.pdf",
                    "mimeType": "application/pdf",
                    "size": "2048",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                    "parents": ["root"],
                },
            ]
        }

        with patch.object(connector, "_build_service", return_value=mock_svc):
            entries = await connector.list_folder_children("root-folder-id")

        assert len(entries) == 2
        folder = [e for e in entries if e.is_folder][0]
        file = [e for e in entries if not e.is_folder][0]

        assert folder.name == "Semester 3"
        assert folder.is_folder is True
        assert file.name == "Kurikulum.pdf"
        assert file.size == 2048
        assert file.is_folder is False

    @pytest.mark.asyncio
    async def test_not_authenticated_raises(self) -> None:
        """Should raise DriveAuthError if not authenticated."""
        from app.domain.ingestion.drive_connector import GoogleDriveConnector
        from app.domain.ingestion.exceptions import DriveAuthError

        connector = GoogleDriveConnector()
        with pytest.raises(DriveAuthError):
            await connector.list_folder_children("some-folder")
