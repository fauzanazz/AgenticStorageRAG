"""Phase 2: Sequential file processor for indexed files.

Reads pending/processing rows from indexed_files and ingests them
one by one using the extracted ingest_single_file() function.
Resumable — picks up where it left off after a crash.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import (
    IndexedFile,
    IndexedFileStatus,
    IngestionJob,
    IngestionStatus,
)
from app.domain.ingestion.orchestrator_tools import ingest_single_file
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)


class FileProcessor:
    """Sequentially processes all pending indexed files for a job."""

    def __init__(
        self,
        db: AsyncSession,
        connector: SourceConnector,
        llm: LLMProvider,
        job: IngestionJob,
        admin_user_id: uuid.UUID,
        force: bool = False,
    ) -> None:
        self._db = db
        self._connector = connector
        self._llm = llm
        self._job = job
        self._admin_user_id = admin_user_id
        self._force = force

    async def process_all(
        self,
        is_cancelled: Any = None,
    ) -> dict[str, int]:
        """Process all pending/processing indexed files.

        Args:
            is_cancelled: Async callable returning True if job was cancelled.

        Returns:
            Dict with processed, failed, skipped counts.
        """
        processed = 0
        failed = 0
        skipped = 0

        # Query pending and processing files (processing = crashed mid-run)
        result = await self._db.execute(
            select(IndexedFile)
            .where(
                IndexedFile.job_id == self._job.id,
                IndexedFile.status.in_([
                    IndexedFileStatus.PENDING.value,
                    IndexedFileStatus.PROCESSING.value,
                ]),
            )
            .order_by(IndexedFile.created_at)
        )
        rows = result.scalars().all()
        files = list(rows)

        logger.info(
            "FileProcessor: %d files to process for job %s",
            len(files), self._job.id,
        )

        for indexed_file in files:
            # Check cancellation
            if is_cancelled and await is_cancelled():
                logger.info("FileProcessor cancelled at file %s", indexed_file.file_name)
                break

            # Mark as processing
            await self._update_file_status(
                indexed_file, IndexedFileStatus.PROCESSING.value,
            )

            try:
                result_dict = await ingest_single_file(
                    db=self._db,
                    connector=self._connector,
                    llm=self._llm,
                    job=self._job,
                    file_id=indexed_file.drive_file_id,
                    file_name=indexed_file.file_name,
                    mime_type=indexed_file.mime_type,
                    folder_path=indexed_file.folder_path,
                    classification=indexed_file.classification,
                    admin_user_id=self._admin_user_id,
                    size_bytes=indexed_file.size_bytes,
                )

                status = result_dict.get("status", "failed")

                if status == "processed":
                    doc_id = result_dict.get("document_id")
                    await self._update_file_status(
                        indexed_file,
                        IndexedFileStatus.COMPLETED.value,
                        document_id=uuid.UUID(doc_id) if doc_id else None,
                    )
                    processed += 1
                elif status == "skipped":
                    await self._update_file_status(
                        indexed_file,
                        IndexedFileStatus.SKIPPED.value,
                    )
                    skipped += 1
                else:
                    error = result_dict.get("error", "Unknown error")
                    await self._update_file_status(
                        indexed_file,
                        IndexedFileStatus.FAILED.value,
                        error_message=error[:500],
                    )
                    failed += 1

            except Exception as e:
                logger.exception(
                    "Failed to process indexed file %s: %s",
                    indexed_file.file_name, e,
                )
                await self._update_file_status(
                    indexed_file,
                    IndexedFileStatus.FAILED.value,
                    error_message=str(e)[:500],
                )
                failed += 1

            # Update job progress counters
            await self._update_job_progress(processed, failed, skipped)

            # Free memory
            gc.collect()

        return {"processed": processed, "failed": failed, "skipped": skipped}

    async def process_until_done(
        self,
        scanning_done: asyncio.Event,
        is_cancelled: Any = None,
        poll_interval: float = 2.0,
    ) -> dict[str, int]:
        """Poll for pending files and process them until scanning is done.

        Args:
            scanning_done: Event that signals all scanners have finished.
            is_cancelled: Async callable returning True if job was cancelled.
            poll_interval: Seconds to sleep when no files are available.

        Returns:
            Dict with processed, failed, skipped counts.
        """
        processed = 0
        failed = 0
        skipped = 0

        while True:
            if is_cancelled and await is_cancelled():
                logger.info("FileProcessor cancelled during polling")
                break

            # Fetch a batch of pending/processing files
            result = await self._db.execute(
                select(IndexedFile)
                .where(
                    IndexedFile.job_id == self._job.id,
                    IndexedFile.status.in_([
                        IndexedFileStatus.PENDING.value,
                        IndexedFileStatus.PROCESSING.value,
                    ]),
                )
                .order_by(IndexedFile.created_at)
                .limit(10)
            )
            files = list(result.scalars().all())

            if not files:
                if scanning_done.is_set():
                    # Final drain: one last check after scanners finished
                    result = await self._db.execute(
                        select(IndexedFile)
                        .where(
                            IndexedFile.job_id == self._job.id,
                            IndexedFile.status.in_([
                                IndexedFileStatus.PENDING.value,
                                IndexedFileStatus.PROCESSING.value,
                            ]),
                        )
                        .order_by(IndexedFile.created_at)
                        .limit(10)
                    )
                    files = list(result.scalars().all())
                    if not files:
                        break
                else:
                    await asyncio.sleep(poll_interval)
                    continue

            for indexed_file in files:
                if is_cancelled and await is_cancelled():
                    logger.info("FileProcessor cancelled at file %s", indexed_file.file_name)
                    return {"processed": processed, "failed": failed, "skipped": skipped}

                await self._update_file_status(
                    indexed_file, IndexedFileStatus.PROCESSING.value,
                )

                try:
                    result_dict = await ingest_single_file(
                        db=self._db,
                        connector=self._connector,
                        llm=self._llm,
                        job=self._job,
                        file_id=indexed_file.drive_file_id,
                        file_name=indexed_file.file_name,
                        mime_type=indexed_file.mime_type,
                        folder_path=indexed_file.folder_path,
                        classification=indexed_file.classification,
                        admin_user_id=self._admin_user_id,
                        size_bytes=indexed_file.size_bytes,
                    )

                    status = result_dict.get("status", "failed")

                    if status == "processed":
                        doc_id = result_dict.get("document_id")
                        await self._update_file_status(
                            indexed_file,
                            IndexedFileStatus.COMPLETED.value,
                            document_id=uuid.UUID(doc_id) if doc_id else None,
                        )
                        processed += 1
                        await self._increment_job_progress(1, 0, 0)
                    elif status == "skipped":
                        await self._update_file_status(
                            indexed_file,
                            IndexedFileStatus.SKIPPED.value,
                        )
                        skipped += 1
                        await self._increment_job_progress(0, 0, 1)
                    else:
                        error = result_dict.get("error", "Unknown error")
                        await self._update_file_status(
                            indexed_file,
                            IndexedFileStatus.FAILED.value,
                            error_message=error[:500],
                        )
                        failed += 1
                        await self._increment_job_progress(0, 1, 0)

                except Exception as e:
                    logger.exception(
                        "Failed to process indexed file %s: %s",
                        indexed_file.file_name, e,
                    )
                    await self._update_file_status(
                        indexed_file,
                        IndexedFileStatus.FAILED.value,
                        error_message=str(e)[:500],
                    )
                    failed += 1
                    await self._increment_job_progress(0, 1, 0)

                gc.collect()

        return {"processed": processed, "failed": failed, "skipped": skipped}

    async def _update_file_status(
        self,
        indexed_file: IndexedFile,
        status: str,
        document_id: uuid.UUID | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an indexed file's status."""
        values: dict[str, Any] = {"status": status}
        if document_id is not None:
            values["document_id"] = document_id
        if error_message is not None:
            values["error_message"] = error_message
        if status in (IndexedFileStatus.COMPLETED.value, IndexedFileStatus.FAILED.value, IndexedFileStatus.SKIPPED.value):
            values["processed_at"] = datetime.now(timezone.utc)

        stmt = (
            sa_update(IndexedFile)
            .where(IndexedFile.id == indexed_file.id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

        # Keep in-memory object in sync
        indexed_file.status = status
        if document_id:
            indexed_file.document_id = document_id

    async def _update_job_progress(
        self,
        processed: int,
        failed: int,
        skipped: int,
    ) -> None:
        """Update job progress counters (absolute values)."""
        stmt = (
            sa_update(IngestionJob)
            .where(
                IngestionJob.id == self._job.id,
                IngestionJob.status != IngestionStatus.CANCELLED,
            )
            .values(
                processed_files=processed,
                failed_files=failed,
                skipped_files=skipped,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._db.execute(stmt)
        await self._db.commit()

        if result.rowcount > 0:
            self._job.processed_files = processed
            self._job.failed_files = failed
            self._job.skipped_files = skipped

    async def _increment_job_progress(
        self,
        p_delta: int,
        f_delta: int,
        s_delta: int,
    ) -> None:
        """Atomically increment job progress counters."""
        values: dict[str, Any] = {}
        if p_delta:
            values["processed_files"] = IngestionJob.processed_files + p_delta
        if f_delta:
            values["failed_files"] = IngestionJob.failed_files + f_delta
        if s_delta:
            values["skipped_files"] = IngestionJob.skipped_files + s_delta

        if not values:
            return

        stmt = (
            sa_update(IngestionJob)
            .where(
                IngestionJob.id == self._job.id,
                IngestionJob.status != IngestionStatus.CANCELLED,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()
