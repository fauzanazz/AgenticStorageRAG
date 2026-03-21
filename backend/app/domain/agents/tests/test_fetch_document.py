"""Tests for the fetch_document agent tool."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.agents.tools.fetch_document import (
    CHUNKS_PER_PAGE,
    MAX_FULL_TEXT_CHARS,
    FetchDocumentTool,
)
from app.domain.documents.models import Document, DocumentChunk, DocumentSource, DocumentStatus


def _make_document(
    *,
    source: DocumentSource = DocumentSource.GOOGLE_DRIVE,
    status: DocumentStatus = DocumentStatus.READY,
    drive_file_id: str | None = "drive-123",
    storage_path: str | None = None,
    file_type: str = "application/pdf",
    filename: str = "report.pdf",
    chunk_count: int = 10,
) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.filename = filename
    doc.file_type = file_type
    doc.status = status
    doc.source = source
    doc.chunk_count = chunk_count
    doc.storage_path = storage_path
    doc.metadata_ = {"drive_file_id": drive_file_id} if drive_file_id else {}
    return doc


def _make_chunk(index: int, doc_id: uuid.UUID) -> MagicMock:
    chunk = MagicMock(spec=DocumentChunk)
    chunk.document_id = doc_id
    chunk.chunk_index = index
    chunk.content = f"Chunk {index} content"
    return chunk


def _mock_db_returning(document: Document | None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = document
    db.execute.return_value = result
    return db


class TestFetchDocumentTool:
    """Tests for FetchDocumentTool."""

    def test_name(self) -> None:
        tool = FetchDocumentTool(db=AsyncMock())
        assert tool.name == "fetch_document"

    def test_description_not_empty(self) -> None:
        tool = FetchDocumentTool(db=AsyncMock())
        assert len(tool.description) > 20

    def test_parameters_schema_has_document_id_required(self) -> None:
        tool = FetchDocumentTool(db=AsyncMock())
        schema = tool.parameters_schema
        assert "document_id" in schema["properties"]
        assert "document_id" in schema["required"]

    @pytest.mark.asyncio
    async def test_invalid_document_id(self) -> None:
        tool = FetchDocumentTool(db=AsyncMock())
        result = await tool.execute(document_id="not-a-uuid")
        assert result["error"] == "Invalid document_id"

    @pytest.mark.asyncio
    async def test_document_not_found(self) -> None:
        db = _mock_db_returning(None)
        tool = FetchDocumentTool(db=db)
        result = await tool.execute(document_id=str(uuid.uuid4()))
        assert result["error"] == "Document not found"

    @pytest.mark.asyncio
    async def test_document_not_ready(self) -> None:
        doc = _make_document(status=DocumentStatus.PROCESSING)
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)
        result = await tool.execute(document_id=str(doc.id))
        assert "not ready" in result["error"]

    @pytest.mark.asyncio
    async def test_full_text_google_drive(self) -> None:
        doc = _make_document(source=DocumentSource.GOOGLE_DRIVE, drive_file_id="abc123")
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        short_text = "This is the full document text."

        with (
            patch.object(tool, "_download", new_callable=AsyncMock, return_value=b"pdf-bytes"),
            patch.object(tool, "_extract_text", new_callable=AsyncMock, return_value=short_text),
        ):
            result = await tool.execute(document_id=str(doc.id))

        assert result["result"]["mode"] == "full"
        assert result["result"]["content"] == short_text
        assert result["result"]["source_url"] == "https://drive.google.com/file/d/abc123/view"
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_full_text_user_upload(self) -> None:
        doc = _make_document(
            source=DocumentSource.UPLOAD,
            drive_file_id=None,
            storage_path="docs/report.pdf",
        )
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        with (
            patch.object(tool, "_download", new_callable=AsyncMock, return_value=b"bytes"),
            patch.object(tool, "_extract_text", new_callable=AsyncMock, return_value="text"),
        ):
            result = await tool.execute(document_id=str(doc.id))

        assert result["result"]["mode"] == "full"
        assert result["result"]["source_url"] is None  # uploads don't have Drive URLs

    @pytest.mark.asyncio
    async def test_large_document_falls_back_to_chunks(self) -> None:
        doc = _make_document(chunk_count=25)
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        large_text = "x" * (MAX_FULL_TEXT_CHARS + 1)
        chunks = [_make_chunk(i, doc.id) for i in range(CHUNKS_PER_PAGE)]

        # First db.execute returns the document, second returns chunks
        chunk_result = MagicMock()
        chunk_result.scalars.return_value.all.return_value = chunks
        db.execute.side_effect = [db.execute.return_value, chunk_result]

        with (
            patch.object(tool, "_download", new_callable=AsyncMock, return_value=b"bytes"),
            patch.object(tool, "_extract_text", new_callable=AsyncMock, return_value=large_text),
        ):
            result = await tool.execute(document_id=str(doc.id))

        assert result["result"]["mode"] == "chunks"
        assert result["result"]["total_chunks"] == 25
        assert result["result"]["chunk_offset"] == 0
        assert result["result"]["chunks_returned"] == CHUNKS_PER_PAGE
        assert "too large" in result["result"]["fallback_reason"]

    @pytest.mark.asyncio
    async def test_chunk_offset_pagination(self) -> None:
        doc = _make_document(chunk_count=25)
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        large_text = "x" * (MAX_FULL_TEXT_CHARS + 1)
        chunks = [_make_chunk(i + 5, doc.id) for i in range(CHUNKS_PER_PAGE)]

        chunk_result = MagicMock()
        chunk_result.scalars.return_value.all.return_value = chunks
        db.execute.side_effect = [db.execute.return_value, chunk_result]

        with (
            patch.object(tool, "_download", new_callable=AsyncMock, return_value=b"bytes"),
            patch.object(tool, "_extract_text", new_callable=AsyncMock, return_value=large_text),
        ):
            result = await tool.execute(document_id=str(doc.id), chunk_offset=5)

        assert result["result"]["chunk_offset"] == 5

    @pytest.mark.asyncio
    async def test_download_failure_falls_back_to_chunks(self) -> None:
        doc = _make_document(chunk_count=10)
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        chunks = [_make_chunk(0, doc.id)]
        chunk_result = MagicMock()
        chunk_result.scalars.return_value.all.return_value = chunks
        db.execute.side_effect = [db.execute.return_value, chunk_result]

        with patch.object(
            tool, "_download", new_callable=AsyncMock, side_effect=Exception("Drive down")
        ):
            result = await tool.execute(document_id=str(doc.id))

        assert result["result"]["mode"] == "chunks"
        assert "Download failed" in result["result"]["fallback_reason"]

    @pytest.mark.asyncio
    async def test_extract_text_returns_empty(self) -> None:
        doc = _make_document()
        db = _mock_db_returning(doc)
        tool = FetchDocumentTool(db=db)

        with (
            patch.object(tool, "_download", new_callable=AsyncMock, return_value=b"bytes"),
            patch.object(tool, "_extract_text", new_callable=AsyncMock, return_value=""),
        ):
            result = await tool.execute(document_id=str(doc.id))

        assert result["error"] == "Could not extract text from this file type"

    @pytest.mark.asyncio
    async def test_drive_source_url(self) -> None:
        doc = _make_document(drive_file_id="xyz789")
        url = FetchDocumentTool._build_source_url(doc)
        assert url == "https://drive.google.com/file/d/xyz789/view"

    @pytest.mark.asyncio
    async def test_upload_source_url_is_none(self) -> None:
        doc = _make_document(source=DocumentSource.UPLOAD, drive_file_id=None)
        url = FetchDocumentTool._build_source_url(doc)
        assert url is None
