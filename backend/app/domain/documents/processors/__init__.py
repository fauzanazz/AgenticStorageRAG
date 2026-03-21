"""Processor registry.

Maps file types to their processor implementations.
To add a new format, import the processor and add to PROCESSOR_REGISTRY.
"""

from __future__ import annotations

from app.domain.documents.interfaces import AbstractDocumentProcessor
from app.domain.documents.processors.docx import DocxProcessor
from app.domain.documents.processors.pdf import PdfProcessor

# Registry of all available processors
_PROCESSORS: list[AbstractDocumentProcessor] = [
    PdfProcessor(),
    DocxProcessor(),
]


def get_processor(file_type: str) -> AbstractDocumentProcessor | None:
    """Get the appropriate processor for a file type.

    Args:
        file_type: MIME type or extension (e.g., "application/pdf", "docx", ".pdf")

    Returns:
        Processor instance, or None if unsupported
    """
    for processor in _PROCESSORS:
        if processor.can_process(file_type):
            return processor
    return None


def get_supported_types() -> list[str]:
    """Get all supported file types across all processors.

    Returns:
        Flat list of all supported MIME types and extensions
    """
    types: list[str] = []
    for processor in _PROCESSORS:
        types.extend(processor.supported_types)
    return types
