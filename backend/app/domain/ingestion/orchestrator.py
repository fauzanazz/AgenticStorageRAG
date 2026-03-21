"""Ingestion orchestrator -- parallel pipeline for Google Drive ingestion.

Architecture
~~~~~~~~~~~~
Scanning and processing run in parallel via asyncio.gather:
  - 2 scanner workers BFS different subtrees, inserting indexed_files rows
  - 1 processor worker polls indexed_files and ingests them as they appear

The processor stops once both scanners finish and no pending files remain.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
    PendingRollbackError,
    ResourceClosedError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ingestion.drive_connector import SUPPORTED_MIME_TYPES
from app.domain.ingestion.exceptions import IngestionError
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.pipeline import PipelineConfig, StagePipeline
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.scanner import DriveScanner, _SKIP_MIME
from app.domain.ingestion.schemas import DriveFolderEntry
from app.infra.llm import LLMProvider
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

_RETRY_EXCEPTIONS = (
    DBAPIError,
    InterfaceError,
    OperationalError,
    OSError,
    ConnectionError,
    PendingRollbackError,
    ResourceClosedError,
)


async def _db_retry(
    coro_fn: Any,
    *,
    db: AsyncSession | None = None,
    retries: int = 3,
    delay: float = 1.0,
) -> Any:
    """Retry a DB coroutine on transient connection errors (pgbouncer drops).

    If ``db`` is provided, issues a rollback before each retry to clear
    PendingRollbackError states left by prior failed queries.
    """
    for attempt in range(1, retries + 1):
        try:
            return await coro_fn()
        except _RETRY_EXCEPTIONS as exc:
            if attempt == retries:
                logger.error("DB operation failed after %d retries: %s", retries, exc)
                raise
            if db is not None:
                try:
                    await db.rollback()
                except Exception:
                    pass
            logger.warning(
                "DB connection error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, retries, delay, exc,
            )
            await asyncio.sleep(delay)
            delay *= 2  # exponential backoff


async def _check_cancelled(session_factory: Any, job_id: uuid.UUID) -> bool:
    """Session-safe cancellation check for parallel workers.

    Uses a fresh session from the factory each time so a dead pooled
    connection never crashes the caller.
    """
    async def _query() -> bool:
        async with session_factory() as db:
            result = await db.execute(
                select(IngestionJob.status).where(IngestionJob.id == job_id)
            )
            return result.scalar_one_or_none() == IngestionStatus.CANCELLED

    try:
        return await _db_retry(_query)
    except _RETRY_EXCEPTIONS:
        # Connection truly dead — assume not cancelled so the job can finish gracefully
        return False


class IngestionOrchestrator:
    """Parallel orchestrator for Google Drive ingestion.

    Runs 2 scanner workers and 1 processor worker concurrently via asyncio.gather.
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageClient,
        connector: SourceConnector,
        llm: LLMProvider,
        user_settings: "Any | None" = None,
        session_factory: Any = None,
    ) -> None:
        self._db = db
        self._storage = storage
        self._connector = connector
        self._llm = llm.with_user_settings(user_settings) if user_settings is not None else llm
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            import app.infra.database as _db_module
            self._session_factory = _db_module._session_factory

    async def _is_cancelled(self, job: IngestionJob) -> bool:
        """Check the database to see if the job has been cancelled externally."""
        async def _query() -> bool:
            async with self._session_factory() as db:
                result = await db.execute(
                    select(IngestionJob.status).where(IngestionJob.id == job.id)
                )
                current_status = result.scalar_one_or_none()
                if current_status == IngestionStatus.CANCELLED:
                    job.status = IngestionStatus.CANCELLED
                    return True
                return False

        try:
            return await _db_retry(_query)
        except _RETRY_EXCEPTIONS:
            return False

    async def _update_job_status(
        self,
        job: IngestionJob,
        status: IngestionStatus,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        """Persist job status using a direct SQL UPDATE.

        Uses an atomic WHERE guard (status != CANCELLED) so that a concurrent
        cancel from the API server is never overwritten.
        Retries on transient connection errors from pgbouncer.
        """
        from sqlalchemy import update as sa_update

        values: dict[str, Any] = {"status": status}

        if error_message is not None:
            values["error_message"] = error_message

        if completed:
            values["completed_at"] = datetime.now(timezone.utc)

        async def _do_update() -> int:
            async with self._session_factory() as db:
                stmt = (
                    sa_update(IngestionJob)
                    .where(
                        IngestionJob.id == job.id,
                        IngestionJob.status != IngestionStatus.CANCELLED,
                    )
                    .values(**values)
                    .execution_options(synchronize_session=False)
                )
                result = await db.execute(stmt)
                await db.commit()
                return result.rowcount  # type: ignore[return-value]

        try:
            rowcount = await _db_retry(_do_update)
        except _RETRY_EXCEPTIONS:
            logger.error("Failed to update job %s status to %s after retries", job.id, status)
            return

        if rowcount == 0:
            job.status = IngestionStatus.CANCELLED
            return

        job.status = status
        if error_message is not None:
            job.error_message = error_message
        if completed:
            job.completed_at = datetime.now(timezone.utc)

    async def _index_root_files(
        self,
        job: IngestionJob,
        files: list[DriveFolderEntry],
        force: bool,
    ) -> int:
        """Classify and insert root-level files directly (before spawning workers)."""
        if not files:
            return 0

        # Classify via LLM
        scanner = DriveScanner(
            db=self._db,
            connector=self._connector,
            llm=self._llm,
            job=job,
        )
        classifications = await scanner._classify_folder_files(files, "")

        skip_file_ids: set[str] = set()
        if not force:
            skip_file_ids = await scanner._find_already_ingested(
                [f.file_id for f in files]
            )

        count = await scanner._insert_indexed_files(
            files, "", classifications, skip_file_ids,
        )

        if count:
            await scanner._increment_total_files(count)
        skipped_count = sum(1 for f in files if f.file_id in skip_file_ids)
        if skipped_count:
            await scanner._increment_skipped_files(skipped_count)

        logger.info(
            "Root files indexed: %d inserted, %d skipped",
            count, skipped_count,
        )
        return count

    async def run(
        self,
        job: IngestionJob,
        admin_user_id: uuid.UUID,
        force: bool = False,
        retry: bool = False,
    ) -> IngestionJob:
        """Execute an ingestion job with parallel scanning and processing.

        Args:
            job: The IngestionJob to track progress on.
            admin_user_id: User ID to associate ingested documents with.
            force: If True, re-ingest files even if already processed.
            retry: If True, skip scanning and only process pending IndexedFiles.

        Returns:
            Updated IngestionJob with final status.
        """
        # Cache job ID as a plain UUID so error handlers never trigger
        # a lazy load on a dead session (MissingGreenlet).
        job_id = job.id

        try:
            # 1. Authenticate
            authenticated = await self._connector.authenticate()
            if not authenticated:
                await self._update_job_status(
                    job,
                    IngestionStatus.FAILED,
                    error_message="Google Drive authentication failed",
                    completed=True,
                )
                return job

            await self._update_job_status(job, IngestionStatus.PROCESSING)

            if await self._is_cancelled(job):
                return job

            # Set up signaling
            scanning_done = asyncio.Event()

            if retry:
                # Retry mode: scanning already done, IndexedFiles already exist.
                # Just signal scanning complete and run the processor.
                scanning_done.set()
                logger.info(
                    "Retry mode: skipping scanning, processing pending files for job %s",
                    job.id,
                )
            else:
                # 2. Discover top-level children of root folder
                root_folder_id = job.folder_id or "root"
                entries = await self._connector.list_folder_children(root_folder_id)

                subfolders: list[tuple[str, str]] = []
                root_files: list[DriveFolderEntry] = []
                for entry in entries:
                    if entry.is_folder:
                        subfolders.append((entry.file_id, entry.name))
                    elif entry.mime_type not in _SKIP_MIME and entry.mime_type in SUPPORTED_MIME_TYPES:
                        root_files.append(entry)

                # 3. Index root-level files directly (typically few)
                await self._index_root_files(job, root_files, force)

                # 4. Split subfolders between 2 scanner workers (round-robin)
                seeds_a: list[tuple[str, str]] = []
                seeds_b: list[tuple[str, str]] = []
                for i, folder in enumerate(subfolders):
                    (seeds_a if i % 2 == 0 else seeds_b).append(folder)

            # Define workers
            async def processor_worker() -> None:
                pipeline = StagePipeline(
                    session_factory=self._session_factory,
                    connector=self._connector,
                    llm=self._llm,
                    job=job,
                    admin_user_id=admin_user_id,
                    config=PipelineConfig.from_settings(),
                )
                await pipeline.run(
                    scanning_done,
                    is_cancelled=lambda: _check_cancelled(
                        self._session_factory, job.id
                    ),
                )

            # Run scanning + processing
            if retry:
                await processor_worker()
            else:
                async def scanner_worker(seeds: list[tuple[str, str]], worker_id: int) -> None:
                    if not seeds:
                        return
                    async with self._session_factory() as db:
                        scanner = DriveScanner(db, self._connector, self._llm, job)
                        await scanner.scan_seeds(
                            seeds,
                            force=force,
                            is_cancelled=lambda: _check_cancelled(self._session_factory, job.id),
                        )

                async def scanning_phase() -> None:
                    try:
                        await asyncio.gather(
                            scanner_worker(seeds_a, 0),
                            scanner_worker(seeds_b, 1),
                        )
                    finally:
                        scanning_done.set()

                await asyncio.gather(scanning_phase(), processor_worker())

            if await self._is_cancelled(job):
                return job

            # 8. Finalize — read counters from DB for accuracy.
            # Return plain values, not ORM objects, to avoid lazy-load
            # on a closed session (MissingGreenlet).
            async def _refresh_counters() -> dict[str, int] | None:
                async with self._session_factory() as db:
                    r = await db.execute(
                        select(
                            IngestionJob.total_files,
                            IngestionJob.processed_files,
                            IngestionJob.failed_files,
                            IngestionJob.skipped_files,
                        ).where(IngestionJob.id == job.id)
                    )
                    row = r.one_or_none()
                    if row is None:
                        return None
                    return {
                        "total_files": row[0],
                        "processed_files": row[1],
                        "failed_files": row[2],
                        "skipped_files": row[3],
                    }

            try:
                counters = await _db_retry(_refresh_counters)
            except _RETRY_EXCEPTIONS:
                counters = None
            if counters:
                job.total_files = counters["total_files"]
                job.processed_files = counters["processed_files"]
                job.failed_files = counters["failed_files"]
                job.skipped_files = counters["skipped_files"]

            error_msg = None
            if job.failed_files > 0:
                error_msg = f"{job.failed_files} files failed during ingestion"

            await self._update_job_status(
                job,
                IngestionStatus.COMPLETED,
                error_message=error_msg,
                completed=True,
            )

            logger.info(
                "Ingestion complete (job %s): %d processed, %d failed, %d skipped",
                job.id,
                job.processed_files,
                job.failed_files,
                job.skipped_files,
            )
            return job

        except Exception as e:
            logger.exception("Ingestion orchestrator failed (job %s)", job_id)
            try:
                await self._update_job_status(
                    job,
                    IngestionStatus.FAILED,
                    error_message=str(e)[:500],
                    completed=True,
                )
            except Exception:
                logger.error("Could not persist FAILED status for job %s", job_id)
            raise IngestionError(str(e)) from e
