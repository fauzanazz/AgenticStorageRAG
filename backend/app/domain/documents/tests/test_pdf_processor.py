"""Tests for document processors - PDF."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from app.domain.documents.processors.pdf import PdfProcessor


def _make_page_dict(text: str, page: int = 0) -> dict:
    """Build a minimal pymupdf4llm page-chunk dict."""
    return {
        "metadata": {"page": page, "title": "", "author": ""},
        "text": text,
    }


class TestPdfProcessor:
    """Tests for PdfProcessor."""

    def setup_method(self) -> None:
        self.processor = PdfProcessor()

    def test_supported_types(self) -> None:
        assert "application/pdf" in self.processor.supported_types
        assert "pdf" in self.processor.supported_types
        assert ".pdf" in self.processor.supported_types

    def test_can_process_pdf(self) -> None:
        assert self.processor.can_process("application/pdf") is True
        assert self.processor.can_process("pdf") is True
        assert self.processor.can_process(".pdf") is True
        assert self.processor.can_process("docx") is False
        assert self.processor.can_process("text/plain") is False

    @pytest.mark.asyncio
    async def test_process_empty_pdf(self) -> None:
        """Should return 0 chunks and correct metadata for a blank PDF."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)

        with (
            patch("app.domain.documents.processors.pdf.fitz.open", return_value=mock_doc),
            patch(
                "app.domain.documents.processors.pdf.pymupdf4llm.to_markdown",
                return_value=[_make_page_dict("")],
            ),
        ):
            result = await self.processor.process(b"fake-pdf-bytes")

        assert result.page_count == 1
        assert result.metadata["format"] == "pdf"
        assert result.chunks == []
        assert result.total_characters == 0

    @pytest.mark.asyncio
    async def test_process_single_page_markdown(self) -> None:
        """Should produce chunks from Markdown page text."""
        page_text = "# Section\n\nThis is some content about a topic."

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)

        with (
            patch("app.domain.documents.processors.pdf.fitz.open", return_value=mock_doc),
            patch(
                "app.domain.documents.processors.pdf.pymupdf4llm.to_markdown",
                return_value=[_make_page_dict(page_text, page=0)],
            ),
        ):
            result = await self.processor.process(b"fake-pdf-bytes")

        assert result.page_count == 1
        assert result.metadata["format"] == "pdf"
        assert len(result.chunks) >= 1
        assert result.chunks[0].page_number == 1  # 0-based → 1-based
        assert "Section" in result.chunks[0].content

    @pytest.mark.asyncio
    async def test_process_metadata_extracted(self) -> None:
        """Should pull title and author from the first page metadata."""
        page_dict = {
            "metadata": {"page": 0, "title": "My Doc", "author": "Alice"},
            "text": "Some content here.",
        }

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)

        with (
            patch("app.domain.documents.processors.pdf.fitz.open", return_value=mock_doc),
            patch(
                "app.domain.documents.processors.pdf.pymupdf4llm.to_markdown",
                return_value=[page_dict],
            ),
        ):
            result = await self.processor.process(b"fake-pdf-bytes")

        assert result.metadata["title"] == "My Doc"
        assert result.metadata["author"] == "Alice"

    @pytest.mark.asyncio
    async def test_process_returns_processing_result(self) -> None:
        """ProcessingResult should always have required attributes."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)

        with (
            patch("app.domain.documents.processors.pdf.fitz.open", return_value=mock_doc),
            patch(
                "app.domain.documents.processors.pdf.pymupdf4llm.to_markdown",
                return_value=[],
            ),
        ):
            result = await self.processor.process(b"fake-pdf-bytes")

        assert hasattr(result, "chunks")
        assert hasattr(result, "metadata")
        assert hasattr(result, "page_count")
        assert hasattr(result, "total_characters")

    @pytest.mark.asyncio
    async def test_chunk_indices_are_globally_sequential(self) -> None:
        """Chunks from multiple pages must have sequential global indices."""
        pages = [
            _make_page_dict("A " * 600, page=0),
            _make_page_dict("B " * 600, page=1),
        ]

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)

        with (
            patch("app.domain.documents.processors.pdf.fitz.open", return_value=mock_doc),
            patch(
                "app.domain.documents.processors.pdf.pymupdf4llm.to_markdown",
                return_value=pages,
            ),
        ):
            result = await self.processor.process(b"fake-pdf-bytes")

        indices = [c.chunk_index for c in result.chunks]
        assert indices == list(range(len(result.chunks)))
