"""Tests for the ingestion orchestrator agent and tools."""

import json
import uuid
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
# IngestFileTool
# ---------------------------------------------------------------------------


class TestIngestFileTool:
    """Test the ingest_file tool."""

    @pytest.mark.asyncio
    async def test_ingest_success(self) -> None:
        """Should download, process, and commit a file."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        # Deduplication query returns no existing row
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_db.execute.return_value = mock_exec_result
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.download_file.return_value = (b"fake pdf", "doc.pdf")

        # Mock processor
        mock_processing_result = MagicMock()
        mock_processing_result.chunks = [
            MagicMock(chunk_index=0, content="chunk text", page_number=1, metadata={}),
        ]
        mock_processing_result.metadata = {"page_count": 1}

        tool = IngestFileTool(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            job=MagicMock(metadata_={}),
            llm=MagicMock(),
        )

        with (
            patch("app.domain.ingestion.orchestrator_tools.get_processor") as mock_get_proc,
            patch.object(tool, "_embed_chunks", return_value=1),
            patch.object(tool, "_extract_knowledge_graph", return_value={"entities_created": 2, "relationships_created": 1}),
            patch.object(tool, "_record_file_event", new_callable=AsyncMock),
        ):
            mock_processor = AsyncMock()
            mock_processor.process.return_value = mock_processing_result
            mock_get_proc.return_value = mock_processor

            result = await tool.execute(
                file_id="drive-file-1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                folder_path="Informatika/Semester 3",
                classification={"major": "Informatika"},
                admin_user_id=str(uuid.uuid4()),
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
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()

        tool = IngestFileTool(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            job=MagicMock(metadata_={}),
            llm=MagicMock(),
        )

        with patch("app.domain.ingestion.orchestrator_tools.get_processor", return_value=None):
            result = await tool.execute(
                file_id="file-1",
                file_name="image.png",
                mime_type="image/png",
                admin_user_id=str(uuid.uuid4()),
            )

        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_ingest_download_error(self) -> None:
        """Should return failed status on download error."""
        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_db.execute.return_value = mock_exec_result
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.download_file.side_effect = Exception("Network error")

        tool = IngestFileTool(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            job=MagicMock(metadata_={}),
            llm=MagicMock(),
        )

        with (
            patch("app.domain.ingestion.orchestrator_tools.get_processor") as mock_get_proc,
            patch.object(tool, "_record_file_event", new_callable=AsyncMock),
        ):
            mock_get_proc.return_value = AsyncMock()
            result = await tool.execute(
                file_id="file-1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                admin_user_id=str(uuid.uuid4()),
            )

        assert result["status"] == "failed"
        assert "Network error" in result["error"]


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
# IngestionOrchestrator
# ---------------------------------------------------------------------------


class TestIngestionOrchestrator:
    """Test the orchestrator agent loop."""

    @pytest.mark.asyncio
    async def test_auth_failure_marks_job_failed(self) -> None:
        """Should fail the job if Drive auth fails."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = False
        mock_llm = AsyncMock()

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
        )

        result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.FAILED
        assert "authentication failed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_agent_loop_executes_tools(self) -> None:
        """Should execute tool calls from LLM and terminate on text response."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_connector.list_folder_children.return_value = []
        mock_llm = AsyncMock()

        # First LLM call: returns a scan_folder tool call
        first_response = MagicMock()
        first_choice = MagicMock()
        first_message = MagicMock()
        first_tool_call = MagicMock()
        first_tool_call.id = "call_1"
        first_tool_call.function.name = "scan_folder"
        first_tool_call.function.arguments = json.dumps({"folder_id": "root-folder-id"})
        first_message.tool_calls = [first_tool_call]
        first_message.content = None
        first_choice.message = first_message
        first_response.choices = [first_choice]

        # Second LLM call: returns a text response (done)
        second_response = MagicMock()
        second_choice = MagicMock()
        second_message = MagicMock()
        second_message.tool_calls = None
        second_message.content = "Ingestion complete. Scanned 1 folder, found 0 files."
        second_choice.message = second_message
        second_response.choices = [second_choice]

        # First call: scan_folder tool call; second call: text response (done)
        no_tool_response = MagicMock()
        no_tool_choice = MagicMock()
        no_tool_message = MagicMock()
        no_tool_message.tool_calls = None
        no_tool_message.content = "Ingestion complete. Scanned 1 folder, found 0 files."
        no_tool_choice.message = no_tool_message
        no_tool_response.choices = [no_tool_choice]

        mock_llm.complete_for_ingestion.side_effect = [first_response, no_tool_response]

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
        )

        result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        assert result.status == IngestionStatus.COMPLETED
        assert mock_llm.complete_for_ingestion.call_count == 2
        assert mock_connector.list_folder_children.await_count == 1
        assert "orchestrator_summary" in result.metadata_

    @pytest.mark.asyncio
    async def test_unknown_tool_handled_gracefully(self) -> None:
        """Should handle unknown tool calls without crashing."""
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_connector = AsyncMock()
        mock_connector.authenticate.return_value = True
        mock_llm = AsyncMock()

        # LLM calls a non-existent tool, then finishes
        first_response = MagicMock()
        first_choice = MagicMock()
        first_message = MagicMock()
        bad_tool_call = MagicMock()
        bad_tool_call.id = "call_bad"
        bad_tool_call.function.name = "nonexistent_tool"
        bad_tool_call.function.arguments = "{}"
        first_message.tool_calls = [bad_tool_call]
        first_message.content = None
        first_choice.message = first_message
        first_response.choices = [first_choice]

        second_response = MagicMock()
        second_choice = MagicMock()
        second_message = MagicMock()
        second_message.tool_calls = None
        second_message.content = "Done."
        second_choice.message = second_message
        second_response.choices = [second_choice]

        mock_llm.complete.side_effect = [first_response, second_response]

        job = _make_job()
        orchestrator = IngestionOrchestrator(
            db=mock_db,
            storage=mock_storage,
            connector=mock_connector,
            llm=mock_llm,
        )

        result = await orchestrator.run(job, admin_user_id=uuid.uuid4())

        # Should complete without error
        assert result.status == IngestionStatus.COMPLETED


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
