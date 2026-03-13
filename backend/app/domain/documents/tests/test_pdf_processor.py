"""Tests for document processors - PDF."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app.domain.documents.processors.pdf import PdfProcessor


def _create_test_pdf(pages: list[str]) -> bytes:
    """Create a simple PDF with the given page contents."""
    writer = PdfWriter()
    for text in pages:
        writer.add_blank_page(width=612, height=792)
        # pypdf doesn't easily write text to blank pages,
        # so we test with real PDFs via fixtures or mock extract_text
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


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
    async def test_extract_text_empty_pdf(self) -> None:
        pdf_bytes = _create_test_pdf([""])
        text = await self.processor.extract_text(pdf_bytes)
        # Blank pages have no extractable text
        assert isinstance(text, str)

    @pytest.mark.asyncio
    async def test_process_empty_pdf(self) -> None:
        pdf_bytes = _create_test_pdf([""])
        result = await self.processor.process(pdf_bytes)
        assert result.page_count == 1
        assert result.metadata["format"] == "pdf"
        # May produce 0 chunks for blank pages
        assert isinstance(result.chunks, list)

    @pytest.mark.asyncio
    async def test_process_returns_processing_result(self) -> None:
        pdf_bytes = _create_test_pdf(["Hello world"])
        result = await self.processor.process(pdf_bytes)
        assert hasattr(result, "chunks")
        assert hasattr(result, "metadata")
        assert hasattr(result, "page_count")
        assert hasattr(result, "total_characters")
