"""DOCX document processor.

Extracts text from DOCX files using python-docx, splits into chunks
with paragraph-level structure preservation.
"""

from __future__ import annotations

import io
import logging

from docx import Document as DocxDocument

from app.domain.documents.processors.base import BaseProcessor
from app.domain.documents.schemas import ChunkData, ProcessingResult

logger = logging.getLogger(__name__)


class DocxProcessor(BaseProcessor):
    """Processor for DOCX (Microsoft Word) files.

    Extracts text from paragraphs and tables, preserving structure.
    """

    @property
    def supported_types(self) -> list[str]:
        return [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
            ".docx",
        ]

    async def extract_text(self, file_content: bytes) -> str:
        """Extract all text from a DOCX file.

        Args:
            file_content: Raw DOCX bytes

        Returns:
            All text concatenated with paragraph breaks
        """
        doc = DocxDocument(io.BytesIO(file_content))
        parts: list[str] = []

        # Extract paragraphs
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)

        # Extract table content
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    parts.append(row_text)

        return "\n\n".join(parts)

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Process a DOCX into chunks with structure preservation."""
        doc = DocxDocument(io.BytesIO(file_content))

        metadata = {
            "format": "docx",
        }

        # Extract doc properties
        if doc.core_properties:
            if doc.core_properties.title:
                metadata["title"] = doc.core_properties.title
            if doc.core_properties.author:
                metadata["author"] = doc.core_properties.author

        # Build sections by heading structure
        sections: list[dict[str, str | list[str]]] = []
        current_heading = ""
        current_paragraphs: list[str] = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Detect headings
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                # Save previous section
                if current_paragraphs:
                    sections.append({
                        "heading": current_heading,
                        "paragraphs": current_paragraphs,
                    })
                current_heading = text
                current_paragraphs = []
            else:
                current_paragraphs.append(text)

        # Save last section
        if current_paragraphs:
            sections.append({
                "heading": current_heading,
                "paragraphs": current_paragraphs,
            })

        # Extract table content as a separate section
        table_texts: list[str] = []
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    table_texts.append(row_text)

        if table_texts:
            sections.append({
                "heading": "Tables",
                "paragraphs": table_texts,
            })

        # Chunk each section
        all_chunks: list[ChunkData] = []
        total_chars = 0

        for section in sections:
            heading = str(section.get("heading", ""))
            paragraphs = section.get("paragraphs", [])
            assert isinstance(paragraphs, list)
            section_text = "\n\n".join(str(p) for p in paragraphs)

            if heading:
                section_text = f"{heading}\n\n{section_text}"

            total_chars += len(section_text)
            section_chunks = self._split_text(
                section_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            # Add section heading to chunk metadata
            for chunk in section_chunks:
                chunk.metadata["heading"] = heading

            all_chunks.extend(section_chunks)

        # Re-index globally
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i

        logger.info(
            "DOCX processed: %d sections, %d chunks, %d chars",
            len(sections),
            len(all_chunks),
            total_chars,
        )

        return ProcessingResult(
            chunks=all_chunks,
            metadata=metadata,
            page_count=None,  # DOCX doesn't have fixed pages
            total_characters=total_chars,
        )
