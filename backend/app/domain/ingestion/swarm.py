"""Ingestion swarm orchestrator.

Coordinates parallel ingestion of files from a source connector.
Downloads files, processes them through document processors,
builds knowledge graph entries, and tracks progress.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import Document, DocumentSource, DocumentStatus
from app.domain.documents.processors import get_processor
from app.domain.documents.service import DocumentService
from app.domain.ingestion.drive_connector import SUPPORTED_MIME_TYPES
from app.domain.ingestion.exceptions import IngestionError
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import DriveFileInfo
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

# Max concurrent file downloads/processing
MAX_CONCURRENCY = 5


class IngestionSwarm:
    """Orchestrates parallel ingestion of files from source connectors.

    The swarm:
    1. Authenticates with the source
    2. Scans for ingestible files
    3. Filters out already-ingested files
    4. Downloads and processes files in parallel (bounded concurrency)
    5. Tracks progress on the IngestionJob model

    This is the "agent swarm" -- each file is processed by a worker coroutine
    that independently downloads, processes, and creates KG entries.
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageClient,
        connector: SourceConnector,
    ) -> None:
        self._db = db
        self._storage = storage
        self._connector = connector

    async def run(
        self,
        job: IngestionJob,
        admin_user_id: uuid.UUID,
        force: bool = False,
    ) -> IngestionJob:
        """Execute an ingestion job.

        Args:
            job: The IngestionJob to track progress on
            admin_user_id: User ID to associate ingested documents with
            force: If True, re-ingest files even if already processed

        Returns:
            Updated IngestionJob with final status
        """
        try:
            # Phase 1: Authenticate
            job.status = IngestionStatus.SCANNING
            await self._db.commit()

            authenticated = await self._connector.authenticate()
            if not authenticated:
                job.status = IngestionStatus.FAILED
                job.error_message = "Authentication failed"
                job.completed_at = datetime.now(timezone.utc)
                await self._db.commit()
                return job

            # Phase 2: Scan for files
            files = await self._connector.list_files(
                folder_id=job.folder_id,
                supported_types=list(SUPPORTED_MIME_TYPES.keys()),
            )

            if not files:
                job.status = IngestionStatus.COMPLETED
                job.total_files = 0
                job.completed_at = datetime.now(timezone.utc)
                await self._db.commit()
                logger.info("No files found for ingestion")
                return job

            # Phase 3: Filter already-ingested files
            if not force:
                files = await self._filter_new_files(files)

            job.total_files = len(files)
            job.status = IngestionStatus.PROCESSING
            await self._db.commit()

            logger.info(
                "Starting ingestion of %d files (job %s)", len(files), job.id
            )

            # Phase 4: Process files with bounded concurrency
            semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
            results = await asyncio.gather(
                *(
                    self._process_file(
                        file_info=f,
                        admin_user_id=admin_user_id,
                        job=job,
                        semaphore=semaphore,
                    )
                    for f in files
                ),
                return_exceptions=True,
            )

            # Phase 5: Update job with results
            for result in results:
                if isinstance(result, Exception):
                    job.failed_files += 1
                elif result == "skipped":
                    job.skipped_files += 1
                else:
                    job.processed_files += 1

            job.status = IngestionStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)

            if job.failed_files > 0:
                job.error_message = f"{job.failed_files} files failed during ingestion"

            await self._db.commit()

            logger.info(
                "Ingestion complete (job %s): %d processed, %d failed, %d skipped",
                job.id,
                job.processed_files,
                job.failed_files,
                job.skipped_files,
            )

            return job

        except Exception as e:
            job.status = IngestionStatus.FAILED
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(timezone.utc)
            await self._db.commit()
            logger.exception("Ingestion job %s failed", job.id)
            raise IngestionError(str(e)) from e

    async def _process_file(
        self,
        file_info: DriveFileInfo,
        admin_user_id: uuid.UUID,
        job: IngestionJob,
        semaphore: asyncio.Semaphore,
    ) -> str:
        """Process a single file from the source connector.

        Args:
            file_info: File metadata from the source
            admin_user_id: User ID to associate the document with
            job: Parent job for tracking
            semaphore: Concurrency limiter

        Returns:
            "processed" or "skipped"
        """
        async with semaphore:
            logger.info("Processing file: %s (%s)", file_info.name, file_info.file_id)

            try:
                # Determine the target mime type for processing
                target_mime = file_info.mime_type
                if file_info.mime_type == "application/vnd.google-apps.document":
                    target_mime = (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    )

                # Check if we have a processor for this type
                processor = get_processor(target_mime)
                if processor is None:
                    file_ext = SUPPORTED_MIME_TYPES.get(file_info.mime_type, "")
                    processor = get_processor(file_ext)

                if processor is None:
                    logger.warning(
                        "No processor for %s (%s), skipping",
                        file_info.name,
                        file_info.mime_type,
                    )
                    return "skipped"

                # Download from source
                file_content, filename = await self._connector.download_file(
                    file_info.file_id
                )

                # Store in our storage (permanent for base KG)
                doc_id = uuid.uuid4()
                storage_path = f"base_kg/{doc_id}/{filename}"

                await self._storage.upload_file(
                    file_path=storage_path,
                    file_content=file_content,
                    content_type=target_mime,
                )

                # Create document record (permanent, no expiry)
                document = Document(
                    id=doc_id,
                    user_id=admin_user_id,
                    filename=filename,
                    file_type=target_mime,
                    file_size=len(file_content),
                    storage_path=storage_path,
                    status=DocumentStatus.PROCESSING,
                    source=DocumentSource.GOOGLE_DRIVE,
                    is_base_knowledge=True,
                    expires_at=None,  # Permanent
                    metadata_={
                        "drive_file_id": file_info.file_id,
                        "drive_modified_time": file_info.modified_time,
                        "original_mime_type": file_info.mime_type,
                    },
                )
                self._db.add(document)
                await self._db.commit()
                await self._db.refresh(document)

                # Process (extract text + chunk)
                processing_result = await processor.process(file_content)

                # Store chunks
                from app.domain.documents.models import DocumentChunk

                chunks_created = []
                for chunk_data in processing_result.chunks:
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk_data.chunk_index,
                        content=chunk_data.content,
                        page_number=chunk_data.page_number,
                        token_count=len(chunk_data.content.split()),
                        metadata_=chunk_data.metadata,
                    )
                    self._db.add(chunk)
                    chunks_created.append(chunk)

                await self._db.flush()

                document.status = DocumentStatus.READY
                document.chunk_count = len(processing_result.chunks)
                document.metadata_.update(processing_result.metadata)
                document.processed_at = datetime.now(timezone.utc)

                await self._db.commit()

                logger.info(
                    "Ingested %s: %d chunks", filename, len(processing_result.chunks)
                )

                # --- Post-processing: embeddings + KG extraction ---
                await self._embed_chunks(document, chunks_created)
                await self._extract_knowledge_graph(document, chunks_created)

                return "processed"

            except Exception as e:
                logger.exception("Failed to process file %s: %s", file_info.name, e)
                # Track the error in job metadata
                errors = job.metadata_.get("file_errors", [])
                errors.append({
                    "file_id": file_info.file_id,
                    "file_name": file_info.name,
                    "error": str(e)[:200],
                })
                job.metadata_["file_errors"] = errors
                raise

    async def _filter_new_files(
        self, files: list[DriveFileInfo]
    ) -> list[DriveFileInfo]:
        """Filter to new and updated files that need (re-)ingestion.

        Checks by Drive file ID stored in document metadata.
        - New files (file_id not seen before) are included.
        - Updated files (file_id exists but drive_modified_time changed) are
          included AND their stale document is marked for re-processing.
        """
        from sqlalchemy import select, cast, String
        from sqlalchemy.dialects.postgresql import JSONB

        # Get all already-ingested Drive files with their modification times
        result = await self._db.execute(
            select(
                Document.id,
                Document.metadata_["drive_file_id"].astext,
                Document.metadata_["drive_modified_time"].astext,
            ).where(
                Document.source == DocumentSource.GOOGLE_DRIVE,
                Document.is_base_knowledge.is_(True),
                # Only treat READY documents as "already ingested".
                # PROCESSING rows are evidence of a previous crashed run —
                # excluding them here lets the retry re-ingest those files
                # rather than silently skipping them forever.
                Document.status == DocumentStatus.READY,
            )
        )

        existing: dict[str, tuple[Any, str | None]] = {}  # file_id -> (doc_id, modified_time)
        for doc_id, file_id, modified_time in result.all():
            if file_id:
                existing[file_id] = (doc_id, modified_time)

        files_to_process: list[DriveFileInfo] = []
        updated_count = 0

        for f in files:
            if f.file_id not in existing:
                # New file
                files_to_process.append(f)
            else:
                doc_id, stored_modified = existing[f.file_id]
                if f.modified_time and stored_modified and f.modified_time != stored_modified:
                    # Updated file: mark the old document as stale so it gets replaced
                    logger.info(
                        "File updated on Drive: %s (old: %s, new: %s)",
                        f.name,
                        stored_modified,
                        f.modified_time,
                    )
                    # Mark old document for re-processing (downstream can
                    # delete old entities via GraphService.delete_document_entities)
                    old_doc = await self._db.get(Document, doc_id)
                    if old_doc:
                        old_doc.status = DocumentStatus.PROCESSING
                        old_doc.metadata_["_stale"] = True
                        old_doc.metadata_["_replaced_by_modified_time"] = f.modified_time

                    files_to_process.append(f)
                    updated_count += 1
                # else: same file, same modified_time => skip

        if files_to_process:
            new_count = len(files_to_process) - updated_count
            logger.info(
                "Filtered: %d total files, %d new, %d updated, %d unchanged",
                len(files),
                new_count,
                updated_count,
                len(files) - len(files_to_process),
            )

        return files_to_process

    async def _embed_chunks(
        self,
        document: Document,
        chunks: list,
    ) -> None:
        """Generate and store vector embeddings for document chunks.

        Non-fatal: logs errors but does not fail the ingestion.
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
            logger.info(
                "Embedded %d chunks for ingested document %s",
                count,
                document.id,
            )
        except Exception as e:
            logger.error(
                "Embedding generation failed for ingested document %s (non-fatal): %s",
                document.id,
                e,
            )

    async def _extract_knowledge_graph(
        self,
        document: Document,
        chunks: list,
    ) -> None:
        """Extract entities and relationships from chunks into the KG.

        Non-fatal: logs errors but does not fail the ingestion.
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
                "KG extraction for ingested document %s: %d entities, %d relationships",
                document.id,
                result.get("entities_created", 0),
                result.get("relationships_created", 0),
            )
        except Exception as e:
            logger.error(
                "KG extraction failed for ingested document %s (non-fatal): %s",
                document.id,
                e,
            )
