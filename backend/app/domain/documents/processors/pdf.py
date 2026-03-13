"""PDF document processor.

Extracts text from PDF files using pypdf, splits into chunks
with page-level granularity for accurate citations.
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader

from app.domain.documents.processors.base import BaseProcessor
from app.domain.documents.schemas import ChunkData, ProcessingResult

logger = logging.getLogger(__name__)


class PdfProcessor(BaseProcessor):
    """Processor for PDF files.

    Extracts text page by page, preserving page numbers for citations.
    """

    @property
    def supported_types(self) -> list[str]:
        return ["application/pdf", "pdf", ".pdf"]

    async def extract_text(self, file_content: bytes) -> str:
        """Extract all text from a PDF file.

        Args:
            file_content: Raw PDF bytes

        Returns:
            All text concatenated with page breaks
        """
        reader = PdfReader(io.BytesIO(file_content))
        pages_text: list[str] = []

        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)

        return "\n\n".join(pages_text)

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Process a PDF into chunks with page-level tracking.

        Each page is chunked independently so page numbers are accurate.
        """
        reader = PdfReader(io.BytesIO(file_content))
        all_chunks: list[ChunkData] = []
        total_chars = 0

        metadata = {
            "page_count": len(reader.pages),
            "format": "pdf",
        }

        # Extract PDF metadata
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = reader.metadata.title
            if reader.metadata.author:
                metadata["author"] = reader.metadata.author

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            total_chars += len(text)
            page_chunks = self._split_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                page_number=page_num,
            )
            all_chunks.extend(page_chunks)

        # Re-index chunks globally
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i

        logger.info(
            "PDF processed: %d pages, %d chunks, %d chars",
            len(reader.pages),
            len(all_chunks),
            total_chars,
        )

        return ProcessingResult(
            chunks=all_chunks,
            metadata=metadata,
            page_count=len(reader.pages),
            total_characters=total_chars,
        )
