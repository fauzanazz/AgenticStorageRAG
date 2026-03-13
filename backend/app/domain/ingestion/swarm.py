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

                document.status = DocumentStatus.READY
                document.chunk_count = len(processing_result.chunks)
                document.metadata_.update(processing_result.metadata)
                document.processed_at = datetime.now(timezone.utc)

                await self._db.commit()

                logger.info(
                    "Ingested %s: %d chunks", filename, len(processing_result.chunks)
                )
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
        """Filter out files that have already been ingested.

        Checks by Drive file ID stored in document metadata.
        """
        from sqlalchemy import select, cast, String
        from sqlalchemy.dialects.postgresql import JSONB

        # Get all already-ingested Drive file IDs
        result = await self._db.execute(
            select(Document.metadata_["drive_file_id"].astext).where(
                Document.source == DocumentSource.GOOGLE_DRIVE,
                Document.is_base_knowledge.is_(True),
                Document.status.in_([DocumentStatus.READY, DocumentStatus.PROCESSING]),
            )
        )
        existing_ids = {row[0] for row in result.all() if row[0]}

        new_files = [f for f in files if f.file_id not in existing_ids]

        if len(files) != len(new_files):
            logger.info(
                "Filtered: %d total files, %d new, %d already ingested",
                len(files),
                len(new_files),
                len(files) - len(new_files),
            )

        return new_files
