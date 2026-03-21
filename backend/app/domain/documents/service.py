"""Document service.

Handles document lifecycle: upload, processing, retrieval, deletion, and TTL expiry.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, func, select
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
    DashboardStatsResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DriveFileNode,
    DriveFolderNode,
    DriveTreeResponse,
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
        """Process a document: extract text, chunk, store chunks, embed, and extract KG.

        Called by the background worker after upload.
        """
        # Fetch document
        result = await self._db.execute(select(Document).where(Document.id == document_id))
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
            # Drive-sourced documents store a logical reference ("drive://...")
            # rather than a Supabase path — they are never re-processed via
            # this path (ingestion handles them directly at ingest time).
            if not document.storage_path or document.storage_path.startswith("drive://"):
                raise UnsupportedFileTypeError(
                    f"Cannot re-process Drive-sourced document {document_id} "
                    "via the upload pipeline — no Supabase copy exists."
                )
            file_content = await self._storage.download_file(document.storage_path)

            # Process document
            processing_result: ProcessingResult = await processor.process(file_content)

            # Store chunks
            chunk_records = []
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
                chunk_records.append(chunk)

            await self._db.flush()

            # Update document status
            document.status = DocumentStatus.READY
            document.chunk_count = len(processing_result.chunks)
            document.metadata_ = processing_result.metadata

            if processing_result.page_count is not None:
                document.metadata_["page_count"] = processing_result.page_count

            document.processed_at = datetime.now(UTC)
            await self._db.commit()

            logger.info(
                "Document processed: %s (%d chunks)",
                document_id,
                len(processing_result.chunks),
            )

            # --- Post-processing: embeddings + KG extraction ---
            # These run after commit so the chunks have IDs.
            await self._embed_chunks(document, chunk_records)
            await self._extract_knowledge_graph(document, chunk_records)

        except Exception as e:
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)[:500]
            await self._db.commit()
            logger.exception("Document processing failed: %s", document_id)
            raise DocumentProcessingError(str(document_id), str(e)) from e

    async def _embed_chunks(
        self,
        document: Document,
        chunks: list[DocumentChunk],
    ) -> None:
        """Generate and store vector embeddings for document chunks.

        Non-fatal: logs errors but does not fail the document processing.
        """
        if not chunks:
            return

        try:
            from app.domain.knowledge.vector_service import VectorService

            vector_service = VectorService(db=self._db)
            chunk_dicts = [
                {
                    "id": chunk.id,
                    "content": chunk.content,
                    "metadata": chunk.metadata_ or {},
                }
                for chunk in chunks
            ]

            count = await vector_service.embed_chunks(
                chunks=chunk_dicts,
                document_id=document.id,
            )
            await self._db.commit()
            logger.info("Embedded %d chunks for document %s", count, document.id)
        except Exception as e:
            logger.error(
                "Embedding generation failed for document %s (non-fatal): %s",
                document.id,
                e,
            )

    async def _extract_knowledge_graph(
        self,
        document: Document,
        chunks: list[DocumentChunk],
    ) -> None:
        """Extract entities and relationships from chunks into the KG.

        Non-fatal: logs errors but does not fail the document processing.
        """
        if not chunks:
            return

        try:
            from app.domain.knowledge.graph_service import GraphService
            from app.domain.knowledge.kg_builder import KGBuilder
            from app.infra.llm import llm_provider
            from app.infra.neo4j_client import neo4j_client

            graph_service = GraphService(db=self._db, neo4j=neo4j_client)
            kg_builder = KGBuilder(
                graph_service=graph_service,
                llm=llm_provider,
            )

            chunk_dicts = [
                {
                    "content": chunk.content,
                    "metadata": chunk.metadata_ or {},
                }
                for chunk in chunks
            ]

            result = await kg_builder.build_from_chunks(
                chunks=chunk_dicts,
                document_id=document.id,
            )
            await self._db.commit()
            logger.info(
                "KG extraction for document %s: %d entities, %d relationships",
                document.id,
                result.get("entities_created", 0),
                result.get("relationships_created", 0),
            )
        except Exception as e:
            logger.error(
                "KG extraction failed for document %s (non-fatal): %s",
                document.id,
                e,
            )

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
        source: str | None = None,
    ) -> DocumentListResponse:
        """List documents for a user with pagination.

        Args:
            source: Optional filter — 'upload' or 'google_drive'.
        """
        offset = (page - 1) * page_size

        # Build base filters
        filters = [Document.user_id == user_id]
        if source:
            filters.append(Document.source == source)

        # Count total
        count_result = await self._db.execute(select(func.count()).where(*filters))
        total = count_result.scalar() or 0

        # Fetch page
        result = await self._db.execute(
            select(Document)
            .where(*filters)
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

        # Delete from storage (skip Drive-referenced docs — no Supabase copy)
        if document.storage_path and not document.storage_path.startswith("drive://"):
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
        now = datetime.now(UTC)

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

        # Delete storage files in bulk (skip Drive-referenced docs)
        storage_paths = [
            doc.storage_path
            for doc in expired_docs
            if doc.storage_path and not doc.storage_path.startswith("drive://")
        ]
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

    async def get_dashboard_stats(self, user_id: uuid.UUID) -> DashboardStatsResponse:
        """Get aggregated stats for the user dashboard.

        Collects document, chunk, entity, relationship, and embedding counts.
        """
        # Document counts
        total_docs = (
            await self._db.execute(select(func.count()).where(Document.user_id == user_id))
        ).scalar() or 0

        processing_docs = (
            await self._db.execute(
                select(func.count()).where(
                    Document.user_id == user_id,
                    Document.status == DocumentStatus.PROCESSING,
                )
            )
        ).scalar() or 0

        # Chunk count
        total_chunks = (
            await self._db.execute(
                select(func.count(DocumentChunk.id))
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.user_id == user_id)
            )
        ).scalar() or 0

        # Knowledge graph stats (global, not per-user)
        from app.domain.knowledge.models import (
            DocumentEmbedding,
            KnowledgeEntity,
            KnowledgeRelationship,
        )

        total_entities = (
            await self._db.execute(select(func.count(KnowledgeEntity.id)))
        ).scalar() or 0

        total_relationships = (
            await self._db.execute(select(func.count(KnowledgeRelationship.id)))
        ).scalar() or 0

        total_embeddings = (
            await self._db.execute(select(func.count(DocumentEmbedding.id)))
        ).scalar() or 0

        return DashboardStatsResponse(
            total_documents=total_docs,
            total_chunks=total_chunks,
            total_entities=total_entities,
            total_relationships=total_relationships,
            total_embeddings=total_embeddings,
            processing_documents=processing_docs,
        )

    async def get_drive_tree(self) -> DriveTreeResponse:
        """Build a folder tree from indexed Drive files.

        Deduplicates by drive_file_id (latest record wins) and organises
        files into a nested folder structure based on folder_path.
        """
        from app.domain.ingestion.models import IndexedFile

        # Deduplicate: latest record per drive_file_id
        subq = select(
            IndexedFile,
            func.row_number()
            .over(
                partition_by=IndexedFile.drive_file_id,
                order_by=IndexedFile.created_at.desc(),
            )
            .label("rn"),
        ).subquery()
        result = await self._db.execute(select(subq).where(subq.c.rn == 1))
        rows = result.all()

        # Build lookup of folders
        folder_lookup: dict[str, DriveFolderNode] = {}
        root = DriveFolderNode(name="Root", path="")
        folder_lookup[""] = root

        def get_or_create_folder(path: str) -> DriveFolderNode:
            if path in folder_lookup:
                return folder_lookup[path]
            parts = path.split("/")
            parent_path = "/".join(parts[:-1])
            parent = get_or_create_folder(parent_path)
            folder = DriveFolderNode(name=parts[-1], path=path)
            parent.folders.append(folder)
            folder_lookup[path] = folder
            return folder

        total_files = 0
        processed_files = 0
        scanned_files = 0

        for row in rows:
            folder = get_or_create_folder(row.folder_path)
            file_node = DriveFileNode(
                id=row.id,
                drive_file_id=row.drive_file_id,
                file_name=row.file_name,
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
                folder_path=row.folder_path,
                status=row.status,
                document_id=row.document_id,
                created_at=row.created_at,
                processed_at=row.processed_at,
            )
            folder.files.append(file_node)
            total_files += 1
            if row.status == "completed":
                processed_files += 1
            scanned_files += 1

        # Sort folders and files alphabetically, compute counts
        def sort_and_count(node: DriveFolderNode) -> tuple[int, int]:
            node.folders.sort(key=lambda f: f.name.lower())
            node.files.sort(key=lambda f: f.file_name.lower())
            t = len(node.files)
            p = sum(1 for f in node.files if f.status == "completed")
            for child in node.folders:
                ct, cp = sort_and_count(child)
                t += ct
                p += cp
            node.total_files = t
            node.processed_files = p
            return t, p

        sort_and_count(root)

        return DriveTreeResponse(
            root=root,
            total_files=total_files,
            processed_files=processed_files,
            scanned_files=scanned_files,
        )
