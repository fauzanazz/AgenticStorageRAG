"""Base document processor with shared chunking logic.

Contains the text splitting algorithm shared by all processors.
"""

from __future__ import annotations

from app.domain.documents.interfaces import AbstractDocumentProcessor
from app.domain.documents.schemas import ChunkData


class BaseProcessor(AbstractDocumentProcessor):
    """Base class with shared text chunking logic.

    Subclasses only need to implement `extract_text` and `supported_types`.
    The `process` method is provided with a default chunking strategy.
    """

    def _split_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        page_number: int | None = None,
    ) -> list[ChunkData]:
        """Split text into overlapping chunks.

        Uses paragraph boundaries when possible, falling back to
        character-based splitting for long paragraphs.

        Args:
            text: Text to split
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks
            page_number: Page number for all chunks (if from a single page)

        Returns:
            List of ChunkData objects
        """
        if not text.strip():
            return []

        # Split by paragraph boundaries first
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        chunks: list[ChunkData] = []
        current_chunk = ""
        chunk_index = len(chunks)

        for para in paragraphs:
            # If adding this paragraph would exceed chunk_size
            if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
                chunks.append(
                    ChunkData(
                        content=current_chunk.strip(),
                        page_number=page_number,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index = len(chunks)

                # Keep overlap from end of previous chunk
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                current_chunk = (current_chunk + "\n\n" + para).strip() if current_chunk else para

            # Handle single paragraphs larger than chunk_size
            while len(current_chunk) > chunk_size * 1.5:
                # Minimum chars to advance per iteration to guarantee
                # the while loop terminates (prevents infinite loop when
                # the best ". " boundary is before the overlap region).
                min_advance = chunk_size - chunk_overlap

                split_point = current_chunk.rfind(". ", 0, chunk_size)
                if split_point == -1 or split_point + 1 < min_advance:
                    # ". " missing or too early — try word boundary instead
                    split_point = current_chunk.rfind(" ", 0, chunk_size)
                if split_point == -1 or split_point + 1 < min_advance:
                    # No usable boundary — hard cut at min_advance
                    split_point = min_advance - 1

                chunks.append(
                    ChunkData(
                        content=current_chunk[:split_point + 1].strip(),
                        page_number=page_number,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index = len(chunks)

                overlap_start = max(0, split_point + 1 - chunk_overlap)
                current_chunk = current_chunk[overlap_start:].strip()

        # Add remaining text
        if current_chunk.strip():
            chunks.append(
                ChunkData(
                    content=current_chunk.strip(),
                    page_number=page_number,
                    chunk_index=chunk_index,
                )
            )

        # Re-index chunks sequentially
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i

        return chunks
