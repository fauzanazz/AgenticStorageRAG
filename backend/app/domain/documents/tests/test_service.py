"""Tests for document service."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docx import Document as DocxDocument

from app.domain.documents.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.documents.models import Document, DocumentSource, DocumentStatus
from app.domain.documents.service import DocumentService


def _make_test_docx() -> bytes:
    """Create a minimal valid DOCX file."""
    doc = DocxDocument()
    doc.add_paragraph("Test content for processing.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestDocumentServiceUpload:
    """Tests for DocumentService.upload."""

    @pytest.mark.asyncio
    async def test_upload_success(self) -> None:
        mock_db = AsyncMock()
        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(return_value={"path": "test"})

        # Make db.add a regular Mock that sets ORM defaults on the Document
        from datetime import datetime, timezone
        def _fake_add(obj: object) -> None:
            if hasattr(obj, "uploaded_at") and obj.uploaded_at is None:
                obj.uploaded_at = datetime.now(timezone.utc)
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
