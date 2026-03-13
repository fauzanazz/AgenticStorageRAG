"""Document service.

Handles document lifecycle: upload, processing, retrieval, deletion, and TTL expiry.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.documents.exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.documents.models import Document, DocumentChunk, DocumentSource, DocumentStatus
from app.domain.documents.processors import get_processor
from app.domain.documents.schemas import (
    ChunkData,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    ProcessingResult,
)
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document management operations.

    Coordinates between storage, database, and processors.
    """

    def __init__(self, db: AsyncSession, storage: StorageClient) -> None:
        self._db = db
        self._storage = storage

    async def upload(
        self,
        user_id: uuid.UUID,
        filename: str,
        file_content: bytes,
        content_type: str,
    ) -> DocumentUploadResponse:
        """Upload a document and queue it for processing.

        Args:
            user_id: ID of the uploading user
            filename: Original filename
            file_content: Raw file bytes
            content_type: MIME type

        Returns:
            DocumentUploadResponse with ID and status

        Raises:
            UnsupportedFileTypeError: If file type is not supported
            FileTooLargeError: If file exceeds size limit
        """
        settings = get_settings()

        # Validate file type
        file_ext = Path(filename).suffix.lower().lstrip(".")
        processor = get_processor(content_type) or get_processor(file_ext)
        if processor is None:
            raise UnsupportedFileTypeError(content_type)

        # Validate file size
        max_size = settings.max_upload_size_mb * 1024 * 1024
        if len(file_content) > max_size:
            raise FileTooLargeError(len(file_content), max_size)

        # Generate storage path
        doc_id = uuid.uuid4()
        storage_path = f"{user_id}/{doc_id}/{filename}"

        # Calculate TTL expiry
        expires_at = StorageClient.calculate_expiry(settings.upload_ttl_days)

        # Upload to storage
        await self._storage.upload_file(
            file_path=storage_path,
            file_content=file_content,
            content_type=content_type,
        )

        # Create database record
        document = Document(
            id=doc_id,
            user_id=user_id,
            filename=filename,
            file_type=content_type,
            file_size=len(file_content),
            storage_path=storage_path,
            status=DocumentStatus.UPLOADING,
            source=DocumentSource.UPLOAD,
            expires_at=expires_at,
        )

        self._db.add(document)
        await self._db.commit()
        await self._db.refresh(document)

        logger.info("Document uploaded: %s (%s, %d bytes)", doc_id, filename, len(file_content))

        return DocumentUploadResponse(
            id=document.id,
            filename=document.filename,
            file_type=document.file_type,
            file_size=document.file_size,
            status=document.status.value,
            uploaded_at=document.uploaded_at,
            expires_at=document.expires_at,
        )

    async def process_document(self, document_id: uuid.UUID) -> None:
        """Process a document: extract text, chunk, and store chunks.

        Called by the background worker after upload.
        """
        # Fetch document
        result = await self._db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundError(str(document_id))

        # Update status to processing
        document.status = DocumentStatus.PROCESSING
        await self._db.commit()

        try:
            # Get processor
            file_ext = Path(document.filename).suffix.lower().lstrip(".")
            processor = get_processor(document.file_type) or get_processor(file_ext)
            if processor is None:
                raise UnsupportedFileTypeError(document.file_type)

            # Download file from storage
            file_content = await self._storage.download_file(document.storage_path)

            # Process document
            processing_result: ProcessingResult = await processor.process(file_content)

            # Store chunks
            for chunk_data in processing_result.chunks:
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_data.chunk_index,
                    content=chunk_data.content,
                    page_number=chunk_data.page_number,
                    token_count=len(chunk_data.content.split()),  # Rough estimate
                    metadata_=chunk_data.metadata,
                )
                self._db.add(chunk)

            # Update document status
            document.status = DocumentStatus.READY
            document.chunk_count = len(processing_result.chunks)
            document.metadata_ = processing_result.metadata
            document.processed_at = datetime.now(timezone.utc)

            if processing_result.page_count is not None:
                document.metadata_["page_count"] = processing_result.page_count

            await self._db.commit()

            logger.info(
                "Document processed: %s (%d chunks)",
                document_id,
                len(processing_result.chunks),
            )

        except Exception as e:
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)[:500]
            await self._db.commit()
            logger.exception("Document processing failed: %s", document_id)
            raise DocumentProcessingError(str(document_id), str(e)) from e

    async def get_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DocumentResponse:
        """Get a single document by ID, scoped to user.

        Raises:
            DocumentNotFoundError: If document not found or not owned by user
        """
        result = await self._db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundError(str(document_id))

        return DocumentResponse.model_validate(document)

    async def list_documents(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> DocumentListResponse:
        """List documents for a user with pagination."""
        offset = (page - 1) * page_size

        # Count total
        count_result = await self._db.execute(
            select(func.count()).where(Document.user_id == user_id)
        )
        total = count_result.scalar() or 0

        # Fetch page
        result = await self._db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.uploaded_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        documents = result.scalars().all()

        return DocumentListResponse(
            items=[DocumentResponse.model_validate(doc) for doc in documents],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def delete_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a document and its chunks, removing from storage.

        Raises:
            DocumentNotFoundError: If document not found or not owned by user
        """
        result = await self._db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundError(str(document_id))

        # Delete from storage
        try:
            await self._storage.delete_file(document.storage_path)
        except Exception:
            logger.warning("Failed to delete storage file: %s", document.storage_path)

        # Delete from database (cascades to chunks)
        await self._db.delete(document)
        await self._db.commit()

        logger.info("Document deleted: %s", document_id)

    async def cleanup_expired(self) -> int:
        """Delete all expired documents and their storage files.

        Returns:
            Number of documents cleaned up
        """
        now = datetime.now(timezone.utc)

        # Find expired documents
        result = await self._db.execute(
            select(Document).where(
                Document.expires_at.isnot(None),
                Document.expires_at < now,
                Document.status != DocumentStatus.EXPIRED,
            )
        )
        expired_docs = list(result.scalars().all())

        if not expired_docs:
            return 0

        # Delete storage files in bulk
        storage_paths = [doc.storage_path for doc in expired_docs]
        try:
            await self._storage.delete_files(storage_paths)
        except Exception:
            logger.warning("Some storage deletions failed during cleanup")

        # Mark as expired and delete chunks
        expired_ids = [doc.id for doc in expired_docs]
        await self._db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id.in_(expired_ids))
        )

        for doc in expired_docs:
            doc.status = DocumentStatus.EXPIRED

        await self._db.commit()

        logger.info("Cleaned up %d expired documents", len(expired_docs))
        return len(expired_docs)
