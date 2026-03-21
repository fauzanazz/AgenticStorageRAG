"""Documents domain exceptions."""

from __future__ import annotations


class DocumentError(Exception):
    """Base exception for the documents domain."""


class DocumentNotFoundError(DocumentError):
    """Raised when a document is not found."""

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"Document not found: {document_id}")


class UnsupportedFileTypeError(DocumentError):
    """Raised when an uploaded file type is not supported."""

    def __init__(self, file_type: str) -> None:
        self.file_type = file_type
        super().__init__(f"Unsupported file type: {file_type}")


class FileTooLargeError(DocumentError):
    """Raised when an uploaded file exceeds the size limit."""

    def __init__(self, file_size: int, max_size: int) -> None:
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"File too large: {file_size} bytes (max: {max_size} bytes)")


class DocumentProcessingError(DocumentError):
    """Raised when document processing fails."""

    def __init__(self, document_id: str, reason: str) -> None:
        self.document_id = document_id
        self.reason = reason
        super().__init__(f"Processing failed for document {document_id}: {reason}")


class DocumentExpiredError(DocumentError):
    """Raised when trying to access an expired document."""

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"Document has expired: {document_id}")
