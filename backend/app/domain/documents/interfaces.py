"""Documents domain interfaces.

ABCs that define the contracts for document processing.
New file formats are added by implementing AbstractDocumentProcessor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.documents.schemas import ProcessingResult


class AbstractDocumentProcessor(ABC):
    """Base contract for all document processors.

    Each file format (PDF, DOCX, etc.) implements this interface.
    The service layer delegates to the appropriate processor based on file type.

    ## How to add a new format:
    1. Create `processors/your_format.py`
    2. Subclass `AbstractDocumentProcessor`
    3. Implement `supported_types`, `extract_text`, and `process`
    4. Register in `processors/__init__.py`
    """

    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return list of MIME types / extensions this processor handles.

        Examples: ["application/pdf", "pdf"] or ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"]
        """
        ...

    @abstractmethod
    async def extract_text(self, file_content: bytes) -> str:
        """Extract raw text content from the file.

        Args:
            file_content: Raw file bytes

        Returns:
            Extracted text as a single string
        """
        ...

    @abstractmethod
    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Process the file into chunks for RAG.

        This is the main entry point. It extracts text, splits into chunks,
        and returns structured results with metadata.

        Args:
            file_content: Raw file bytes
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between consecutive chunks in characters

        Returns:
            ProcessingResult with chunks and metadata
        """
        ...

    def can_process(self, file_type: str) -> bool:
        """Check if this processor can handle the given file type.

        Args:
            file_type: MIME type or extension string

        Returns:
            True if this processor supports the type
        """
        return file_type.lower() in [t.lower() for t in self.supported_types]
