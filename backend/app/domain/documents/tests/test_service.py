"""Tests for document service."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docx import Document as DocxDocument

from app.domain.documents.exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.documents.models import Document, DocumentSource, DocumentStatus
from app.domain.documents.schemas import ChunkData, ProcessingResult
from app.domain.documents.service import DocumentService


def _make_test_docx() -> bytes:
    """Create a minimal valid DOCX file."""
    doc = DocxDocument()
    doc.add_paragraph("Test content for processing.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_mock_document(
    user_id: uuid.UUID | None = None,
    doc_id: uuid.UUID | None = None,
    status: DocumentStatus = DocumentStatus.READY,
    filename: str = "test.pdf",
    file_type: str = "application/pdf",
) -> MagicMock:
    """Create a mock Document with all fields set to realistic values."""
    mock = MagicMock(spec=Document)
    mock.id = doc_id or uuid.uuid4()
    mock.user_id = user_id or uuid.uuid4()
    mock.filename = filename
    mock.file_type = file_type
    mock.file_size = 1024
    mock.storage_path = f"{mock.user_id}/{mock.id}/{filename}"
    mock.status = status
    mock.source = DocumentSource.UPLOAD
    mock.chunk_count = 5
    mock.error_message = None
    mock.is_base_knowledge = False
    mock.metadata_ = {}
    mock.uploaded_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.processed_at = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    mock.expires_at = datetime(2026, 1, 8, tzinfo=UTC)
    return mock


class TestDocumentServiceUpload:
    """Tests for DocumentService.upload."""

    @pytest.mark.asyncio
    async def test_upload_success(self) -> None:
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(return_value={"path": "test"})

        # Make db.add a regular Mock that sets ORM defaults on the Document
        from datetime import datetime

        def _fake_add(obj: object) -> None:
            if hasattr(obj, "uploaded_at") and obj.uploaded_at is None:
                obj.uploaded_at = datetime.now(UTC)

        mock_db.add = MagicMock(side_effect=_fake_add)

        service = DocumentService(db=mock_db, storage=mock_storage)

        with patch("app.domain.documents.service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.max_upload_size_mb = 50
            settings.upload_ttl_days = 7
            mock_settings.return_value = settings

            result = await service.upload(
                user_id=uuid.uuid4(),
                filename="test.docx",
                file_content=b"fake content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        assert result.filename == "test.docx"
        assert result.status == "uploading"
        mock_storage.upload_file.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_unsupported_type(self) -> None:
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with (
            patch("app.domain.documents.service.get_settings") as mock_settings,
            pytest.raises(UnsupportedFileTypeError),
        ):
            settings = MagicMock()
            settings.max_upload_size_mb = 50
            mock_settings.return_value = settings

            await service.upload(
                user_id=uuid.uuid4(),
                filename="test.txt",
                file_content=b"fake",
                content_type="text/plain",
            )

    @pytest.mark.asyncio
    async def test_upload_file_too_large(self) -> None:
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with (
            patch("app.domain.documents.service.get_settings") as mock_settings,
            pytest.raises(FileTooLargeError),
        ):
            settings = MagicMock()
            settings.max_upload_size_mb = 1  # 1 MB
            mock_settings.return_value = settings

            large_content = b"x" * (2 * 1024 * 1024)  # 2 MB
            await service.upload(
                user_id=uuid.uuid4(),
                filename="test.pdf",
                file_content=large_content,
                content_type="application/pdf",
            )


class TestDocumentServiceGetDocument:
    """Tests for DocumentService.get_document."""

    @pytest.mark.asyncio
    async def test_get_document_not_found(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with pytest.raises(DocumentNotFoundError):
            await service.get_document(
                document_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_get_document_success(self) -> None:
        """get_document() should return DocumentResponse with all fields."""
        user_id = uuid.uuid4()
        doc = _make_mock_document(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        result = await service.get_document(doc.id, user_id)

        assert result.id == doc.id
        assert result.filename == "test.pdf"
        assert result.file_type == "application/pdf"
        assert result.file_size == 1024
        assert result.chunk_count == 5


class TestDocumentServiceDelete:
    """Tests for DocumentService.delete_document."""

    @pytest.mark.asyncio
    async def test_delete_not_found(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with pytest.raises(DocumentNotFoundError):
            await service.delete_document(
                document_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        """delete_document() should remove from storage and DB."""
        user_id = uuid.uuid4()
        doc = _make_mock_document(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        await service.delete_document(doc.id, user_id)

        mock_storage.delete_file.assert_called_once_with(doc.storage_path)
        mock_db.delete.assert_called_once_with(doc)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_storage_failure_still_deletes_from_db(self) -> None:
        """delete_document() should delete from DB even if storage fails."""
        user_id = uuid.uuid4()
        doc = _make_mock_document(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        mock_storage.delete_file.side_effect = Exception("S3 timeout")
        service = DocumentService(db=mock_db, storage=mock_storage)

        await service.delete_document(doc.id, user_id)

        # DB deletion should still happen despite storage error
        mock_db.delete.assert_called_once_with(doc)
        mock_db.commit.assert_called_once()


class TestDocumentServiceCleanup:
    """Tests for DocumentService.cleanup_expired."""

    @pytest.mark.asyncio
    async def test_cleanup_no_expired(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        count = await service.cleanup_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_expired_docs(self) -> None:
        """cleanup_expired() should delete storage files and mark docs as expired."""
        doc1 = _make_mock_document(
            status=DocumentStatus.READY,
        )
        doc1.storage_path = "user1/doc1/file.pdf"
        doc2 = _make_mock_document(
            status=DocumentStatus.READY,
        )
        doc2.storage_path = "user2/doc2/file.docx"

        mock_db = AsyncMock()
        # First execute returns the expired docs, rest are for delete/update ops
        find_result = MagicMock()
        find_result.scalars.return_value.all.return_value = [doc1, doc2]
        mock_db.execute = AsyncMock(return_value=find_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        count = await service.cleanup_expired()

        assert count == 2
        mock_storage.delete_files.assert_called_once_with(
            ["user1/doc1/file.pdf", "user2/doc2/file.docx"]
        )
        assert doc1.status == DocumentStatus.EXPIRED
        assert doc2.status == DocumentStatus.EXPIRED
        mock_db.commit.assert_called()


class TestDocumentServiceProcessDocument:
    """Tests for DocumentService.process_document -- the core pipeline."""

    @pytest.mark.asyncio
    async def test_process_document_not_found(self) -> None:
        """process_document() should raise DocumentNotFoundError."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with pytest.raises(DocumentNotFoundError):
            await service.process_document(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_process_document_success(self) -> None:
        """process_document() should extract text, chunk, and update status to READY."""
        doc = _make_mock_document(
            status=DocumentStatus.UPLOADING,
            filename="test.pdf",
            file_type="application/pdf",
        )
        doc.metadata_ = {}

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        mock_storage = AsyncMock()
        mock_storage.download_file = AsyncMock(return_value=b"fake pdf bytes")

        # Mock the processor
        mock_processor = AsyncMock()
        mock_processor.process.return_value = ProcessingResult(
            chunks=[
                ChunkData(chunk_index=0, content="chunk 1 text", page_number=1, metadata={}),
                ChunkData(chunk_index=1, content="chunk 2 text", page_number=2, metadata={}),
            ],
            metadata={"source": "test"},
            page_count=2,
        )

        service = DocumentService(db=mock_db, storage=mock_storage)

        with (
            patch("app.domain.documents.service.get_processor", return_value=mock_processor),
            patch.object(service, "_embed_chunks", new_callable=AsyncMock) as mock_embed,
            patch.object(service, "_extract_knowledge_graph", new_callable=AsyncMock) as mock_kg,
        ):
            await service.process_document(doc.id)

        # Verify status transitions
        assert doc.status == DocumentStatus.READY
        assert doc.chunk_count == 2
        assert doc.processed_at is not None
        assert doc.metadata_["page_count"] == 2

        # Verify chunks were stored
        assert mock_db.add.call_count == 2  # 2 chunks
        mock_db.commit.assert_called()

        # Verify file was downloaded
        mock_storage.download_file.assert_called_once_with(doc.storage_path)

        # Verify post-processing was called
        mock_embed.assert_called_once()
        mock_kg.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_document_failure_marks_failed(self) -> None:
        """process_document() should mark document as FAILED on error."""
        doc = _make_mock_document(
            status=DocumentStatus.UPLOADING,
            filename="test.pdf",
            file_type="application/pdf",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        mock_storage.download_file.side_effect = Exception("Storage unavailable")

        service = DocumentService(db=mock_db, storage=mock_storage)

        # get_processor is called before download, so we need it to return a valid processor
        mock_processor = AsyncMock()
        with (
            patch("app.domain.documents.service.get_processor", return_value=mock_processor),
            pytest.raises(DocumentProcessingError),
        ):
            await service.process_document(doc.id)

        # Verify document was marked as failed
        assert doc.status == DocumentStatus.FAILED
        assert doc.error_message is not None
        assert "Storage unavailable" in doc.error_message

    @pytest.mark.asyncio
    async def test_process_document_unsupported_type(self) -> None:
        """process_document() should fail for unsupported file types."""
        doc = _make_mock_document(
            status=DocumentStatus.UPLOADING,
            filename="test.xyz",
            file_type="application/unknown",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_storage = AsyncMock()
        service = DocumentService(db=mock_db, storage=mock_storage)

        with (
            patch("app.domain.documents.service.get_processor", return_value=None),
            pytest.raises(DocumentProcessingError),
        ):
            await service.process_document(doc.id)

        assert doc.status == DocumentStatus.FAILED


class TestDocumentExceptions:
    """Tests for document domain exceptions."""

    def test_document_not_found(self) -> None:
        e = DocumentNotFoundError("abc-123")
        assert "abc-123" in str(e)
        assert e.document_id == "abc-123"

    def test_unsupported_file_type(self) -> None:
        e = UnsupportedFileTypeError("text/plain")
        assert "text/plain" in str(e)

    def test_file_too_large(self) -> None:
        e = FileTooLargeError(100, 50)
        assert e.file_size == 100
        assert e.max_size == 50
