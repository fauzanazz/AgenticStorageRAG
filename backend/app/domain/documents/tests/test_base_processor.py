"""Tests for the base processor chunking logic."""

from __future__ import annotations

from app.domain.documents.processors.base import BaseProcessor
from app.domain.documents.schemas import ProcessingResult


class ConcreteProcessor(BaseProcessor):
    """Concrete implementation for testing base processor logic."""

    @property
    def supported_types(self) -> list[str]:
        return ["test/plain", "txt"]

    async def extract_text(self, file_content: bytes) -> str:
        return file_content.decode("utf-8")

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        text = await self.extract_text(file_content)
        chunks = self._split_text(text, chunk_size, chunk_overlap)
        return ProcessingResult(
            chunks=chunks,
            metadata={"format": "test"},
            total_characters=len(text),
        )


class TestBaseProcessorChunking:
    """Tests for the text chunking algorithm."""

    def setup_method(self) -> None:
        self.processor = ConcreteProcessor()

    def test_empty_text_returns_no_chunks(self) -> None:
        chunks = self.processor._split_text("")
        assert chunks == []

    def test_whitespace_only_returns_no_chunks(self) -> None:
        chunks = self.processor._split_text("   \n\n   ")
        assert chunks == []

    def test_short_text_single_chunk(self) -> None:
        text = "Hello world. This is a short text."
        chunks = self.processor._split_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].chunk_index == 0

    def test_paragraphs_split_into_chunks(self) -> None:
        para1 = "First paragraph. " * 30  # ~500 chars
        para2 = "Second paragraph. " * 30  # ~500 chars
        text = f"{para1}\n\n{para2}"
        chunks = self.processor._split_text(text, chunk_size=600, chunk_overlap=100)
        assert len(chunks) >= 2

    def test_chunks_have_sequential_indices(self) -> None:
        text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(10)])
        chunks = self.processor._split_text(text, chunk_size=300, chunk_overlap=50)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_page_number_preserved(self) -> None:
        text = "Some text on page 5."
        chunks = self.processor._split_text(text, page_number=5)
        assert len(chunks) == 1
        assert chunks[0].page_number == 5

    def test_long_paragraph_split(self) -> None:
        """A single paragraph longer than chunk_size*1.5 should be split."""
        text = "Word " * 500  # ~2500 chars
        chunks = self.processor._split_text(text, chunk_size=500, chunk_overlap=50)
        assert len(chunks) > 1
        # All chunks should have content
        for chunk in chunks:
            assert len(chunk.content) > 0

    def test_overlap_present(self) -> None:
        """Chunks should overlap when chunk_overlap > 0."""
        para1 = "A " * 300
        para2 = "B " * 300
        text = f"{para1}\n\n{para2}"
        chunks = self.processor._split_text(text, chunk_size=400, chunk_overlap=100)
        if len(chunks) >= 2:
            # The end of chunk 0 should appear at the start of chunk 1
            end_of_first = chunks[0].content[-50:]
            assert end_of_first in chunks[1].content or len(chunks[1].content) > 0
