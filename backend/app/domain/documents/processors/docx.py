"""DOCX document processor.

Extracts text from DOCX files using python-docx and emits Markdown output.
Headings become ATX-style `#` headers, bold/italic runs are wrapped in
`**`/`_`, tables become GFM pipe tables, and images are referenced with
descriptive alt-text placeholders — so the LLM understands document
structure without needing style information.
"""

from __future__ import annotations

import io
import logging

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.domain.documents.processors.base import BaseProcessor
from app.domain.documents.schemas import ChunkData, ProcessingResult

logger = logging.getLogger(__name__)

# Map python-docx heading style names to ATX Markdown prefix
_HEADING_PREFIX: dict[str, str] = {
    "Heading 1": "#",
    "Heading 2": "##",
    "Heading 3": "###",
    "Heading 4": "####",
    "Heading 5": "#####",
    "Heading 6": "######",
    "Title": "#",
    "Subtitle": "##",
}


def _paragraph_to_md(para: Paragraph) -> str:
    """Convert a single paragraph to a Markdown string.

    Preserves bold (`**text**`) and italic (`_text_`) inline formatting.
    Returns an empty string for blank paragraphs.
    """
    parts: list[str] = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"**_{text}_**"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"_{text}_"
        parts.append(text)

    line = "".join(parts).strip()
    if not line:
        return ""

    style_name = para.style.name if para.style and para.style.name else ""
    prefix = _HEADING_PREFIX.get(style_name, "")
    return f"{prefix} {line}" if prefix else line


def _table_to_md(table: Table) -> str:
    """Convert a python-docx Table to a GFM pipe-table string."""
    rows = table.rows
    if not rows:
        return ""

    md_rows: list[str] = []
    for row_idx, row in enumerate(rows):
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        md_rows.append("| " + " | ".join(cells) + " |")
        if row_idx == 0:
            # Header separator
            md_rows.append("| " + " | ".join("---" for _ in cells) + " |")

    return "\n".join(md_rows)


def _has_images(para: Paragraph) -> bool:
    """Return True if the paragraph contains any inline image.

    Checks DrawingML blip references (modern DOCX) and VML imagedata
    (legacy/compatibility layer). The VML namespace is not registered in
    python-docx's nsmap, so we use the raw URI directly.
    """
    _VML_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
    return bool(
        para._element.findall(".//" + qn("a:blip"))
        or para._element.findall(".//" + _VML_IMAGEDATA)
    )


class DocxProcessor(BaseProcessor):
    """Processor for DOCX (Microsoft Word) files.

    Produces Markdown output so the LLM receives structural cues:
    - Headings → ATX `#` headers
    - Bold/italic runs → `**` / `_` markers
    - Tables → GFM pipe tables
    - Inline images → `![image](image)` placeholder with context note
    """

    @property
    def supported_types(self) -> list[str]:
        return [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
            ".docx",
        ]

    async def extract_text(self, file_content: bytes) -> str:
        """Extract all content as a Markdown string.

        Args:
            file_content: Raw DOCX bytes.

        Returns:
            Full document text in Markdown format.
        """
        md, _ = self._docx_to_markdown(file_content)
        return md

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Process a DOCX into Markdown chunks grouped by heading section."""
        full_md, metadata = self._docx_to_markdown(file_content)

        # Split the full markdown into heading-based sections for chunking.
        # Each section is chunked independently so heading context is preserved.
        sections = self._split_into_sections(full_md)

        all_chunks: list[ChunkData] = []
        total_chars = 0

        for heading, section_md in sections:
            if not section_md.strip():
                continue
            total_chars += len(section_md)
            section_chunks = self._split_text(
                section_md,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
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
            page_count=None,  # DOCX has no fixed pages
            total_characters=total_chars,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _docx_to_markdown(self, file_content: bytes) -> tuple[str, dict]:
        """Convert DOCX bytes to a Markdown string + document metadata.

        Iterates the document body in order, interleaving paragraphs and
        tables as they appear (unlike the old implementation which appended
        all tables at the end).
        """
        doc = DocxDocument(io.BytesIO(file_content))

        metadata: dict = {"format": "docx"}
        if doc.core_properties:
            if doc.core_properties.title:
                metadata["title"] = doc.core_properties.title
            if doc.core_properties.author:
                metadata["author"] = doc.core_properties.author

        # Walk the document body XML in document order so tables appear in
        # the right position relative to surrounding paragraphs.
        body = doc.element.body
        blocks: list[str] = []
        image_counter = 0

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                para = Paragraph(child, doc)
                # Image placeholder
                if _has_images(para):
                    image_counter += 1
                    para_text = _paragraph_to_md(para)
                    caption = f" — {para_text}" if para_text else ""
                    blocks.append(f"![image {image_counter}{caption}](image)")
                    continue

                line = _paragraph_to_md(para)
                if line:
                    blocks.append(line)

            elif tag == "tbl":
                table = Table(child, doc)
                table_md = _table_to_md(table)
                if table_md:
                    blocks.append(table_md)

        return "\n\n".join(blocks), metadata

    def _split_into_sections(self, markdown: str) -> list[tuple[str, str]]:
        """Split a Markdown document into (heading, content) sections.

        Each ATX heading (`#`, `##`, …) starts a new section. Content before
        the first heading is grouped under an empty heading string.
        """
        sections: list[tuple[str, str]] = []
        current_heading = ""
        current_lines: list[str] = []

        for line in markdown.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                # Flush previous section
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append((current_heading, content))
                current_heading = stripped.lstrip("#").strip()
                # Start new section with the heading as the first line so
                # the heading appears in the chunk for retrieval context.
                current_lines = [line]
            else:
                current_lines.append(line)

        # Flush last section
        content = "\n".join(current_lines).strip()
        if content:
            sections.append((current_heading, content))

        return sections
