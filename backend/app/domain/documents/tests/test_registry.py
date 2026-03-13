"""Tests for the processor registry."""

from __future__ import annotations

from app.domain.documents.processors import get_processor, get_supported_types
from app.domain.documents.processors.pdf import PdfProcessor
from app.domain.documents.processors.docx import DocxProcessor


class TestProcessorRegistry:
    """Tests for processor registration and lookup."""

    def test_get_processor_pdf(self) -> None:
        processor = get_processor("application/pdf")
        assert processor is not None
        assert isinstance(processor, PdfProcessor)

    def test_get_processor_pdf_extension(self) -> None:
        processor = get_processor("pdf")
        assert processor is not None
        assert isinstance(processor, PdfProcessor)

    def test_get_processor_docx(self) -> None:
        processor = get_processor("docx")
        assert processor is not None
        assert isinstance(processor, DocxProcessor)

    def test_get_processor_docx_mime(self) -> None:
        processor = get_processor(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert processor is not None
        assert isinstance(processor, DocxProcessor)

    def test_get_processor_unsupported(self) -> None:
        processor = get_processor("text/plain")
        assert processor is None

    def test_get_processor_case_insensitive(self) -> None:
        processor = get_processor("PDF")
        assert processor is not None
        assert isinstance(processor, PdfProcessor)

    def test_get_supported_types(self) -> None:
        types = get_supported_types()
        assert "application/pdf" in types
        assert "pdf" in types
        assert "docx" in types
        assert len(types) >= 6  # 3 per processor
