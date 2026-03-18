"""PDF document processor.

Extracts text from PDF files using pymupdf4llm, which produces structured
Markdown output — preserving headings, bold/italic, tables, and image
references — making it significantly easier for LLMs to comprehend document
structure and understand what images depict.
"""

from __future__ import annotations

import asyncio
import io
import logging

import fitz  # PyMuPDF
import pymupdf4llm

from app.domain.documents.processors.base import BaseProcessor
from app.domain.documents.schemas import ChunkData, ProcessingResult

logger = logging.getLogger(__name__)


class PdfProcessor(BaseProcessor):
    """Processor for PDF files.

    Uses pymupdf4llm to convert each page to Markdown, preserving document
    structure (headings, tables, bold/italic) and inserting image references
    with alt-text so the LLM understands what images contain.

    Chunking is done per page so every chunk's page_number is exact.
    """

    @property
    def supported_types(self) -> list[str]:
        return ["application/pdf", "pdf", ".pdf"]

    async def extract_text(self, file_content: bytes) -> str:
        """Extract all pages as a single Markdown string.

        Args:
            file_content: Raw PDF bytes.

        Returns:
            Full document text in Markdown format.
        """
        doc = fitz.open(stream=io.BytesIO(file_content), filetype="pdf")
        try:
            return await asyncio.to_thread(pymupdf4llm.to_markdown, doc)
        finally:
            doc.close()

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Process a PDF into Markdown chunks with per-page tracking.

        Each page is converted to Markdown independently by pymupdf4llm
        (page_chunks=True), then chunked so that page_number on every
        chunk is exact and citations are accurate.
        """
        def _parse_pdf() -> tuple[list[dict], int]:
            doc = fitz.open(stream=io.BytesIO(file_content), filetype="pdf")
            try:
                page_dicts: list[dict] = pymupdf4llm.to_markdown(doc, page_chunks=True)  # type: ignore[assignment]
                return page_dicts, len(doc)
            finally:
                doc.close()

        page_dicts, page_count = await asyncio.to_thread(_parse_pdf)

        all_chunks: list[ChunkData] = []
        total_chars = 0

        # Pull document-level metadata from the first page's metadata block
        metadata: dict = {"format": "pdf", "page_count": page_count}
        if page_dicts:
            first_meta = page_dicts[0].get("metadata", {})
            if first_meta.get("title"):
                metadata["title"] = first_meta["title"]
            if first_meta.get("author"):
                metadata["author"] = first_meta["author"]

        for page_dict in page_dicts:
            page_md: str = page_dict.get("text", "")
            if not page_md.strip():
                continue

            # page index in metadata is 0-based; we store 1-based for humans
            page_number: int = page_dict.get("metadata", {}).get("page", 0) + 1

            total_chars += len(page_md)
            page_chunks = self._split_text(
                page_md,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                page_number=page_number,
            )
            all_chunks.extend(page_chunks)

        # Re-index chunks globally across all pages
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i

        logger.info(
            "PDF processed: %d pages, %d chunks, %d chars",
            page_count,
            len(all_chunks),
            total_chars,
        )

        return ProcessingResult(
            chunks=all_chunks,
            metadata=metadata,
            page_count=page_count,
            total_characters=total_chars,
        )
