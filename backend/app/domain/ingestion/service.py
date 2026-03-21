"""Ingestion service.

Coordinates ingestion jobs, providing the business logic layer
between the router and the swarm/connectors.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.auth.models import OAuthAccount
    from app.domain.ingestion.drive_connector import GoogleDriveConnector

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.models import AppConfig, IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import (
    DefaultFolderResponse,
    DriveFolderEntry,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionStatsResponse,
    TriggerIngestionRequest,
)
from app.infra.storage import StorageClient

# AppConfig keys for default Drive folder
_CFG_DRIVE_FOLDER_ID = "drive_root_folder_id"
_CFG_DRIVE_FOLDER_NAME = "drive_root_folder_name"

logger = logging.getLogger(__name__)

# A job that has been in an active state (PENDING / SCANNING / PROCESSING)
# for longer than this is considered a zombie.  The Celery task has
# time_limit=7200 (2 h), so anything beyond that is guaranteed dead.
# We add a small buffer for clock skew / startup overhead.
_STALE_JOB_THRESHOLD = timedelta(hours=2, minutes=15)


class IngestionService:
    """Service for managing ingestion jobs.

    Provides CRUD operations for jobs and triggers the swarm.
    """

    def __init__(self, db: AsyncSession, storage: StorageClient) -> None:
        self._db = db
        self._storage = storage

    async def trigger_ingestion(
        self,
        request: TriggerIngestionRequest,
        admin_user_id: uuid.UUID,
    ) -> IngestionJobResponse:
        """Trigger a new ingestion job.

        Checks for already-running jobs and creates a new one.
        Stale zombie jobs (started more than ``_STALE_JOB_THRESHOLD`` ago
        but never reached a terminal status) are auto-failed so they
        don't block new triggers forever.

        Args:
            request: Ingestion trigger parameters
            admin_user_id: Admin user who triggered the job

        Returns:
            The created IngestionJob response

        Raises:
            IngestionAlreadyRunningError: If a job is genuinely still active
        """
        active_statuses = [
            IngestionStatus.PENDING,
            IngestionStatus.SCANNING,
            IngestionStatus.PROCESSING,
        ]

        # --- Auto-fail zombie jobs ------------------------------------------
        # A job is "stale" if it has been in an active state for longer than
        # the Celery hard time_limit (2 h) + buffer.  This catches:
        #   - Celery SIGKILL (time_limit) with no cleanup
        #   - Worker crash / restart
        #   - Orchestrator exception where both the orchestrator's own
        #     except handler AND the task's fallback handler failed
        stale_cutoff = datetime.now(UTC) - _STALE_JOB_THRESHOLD

        stale_stmt = (
            sa_update(IngestionJob)
            .where(
                IngestionJob.status.in_(active_statuses),
                IngestionJob.started_at < stale_cutoff,
            )
            .values(
                status=IngestionStatus.FAILED,
                error_message="Auto-failed: job exceeded maximum runtime and is presumed dead",
                completed_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        stale_result = await self._db.execute(stale_stmt)
        if stale_result.rowcount:
            await self._db.commit()
            logger.warning(
                "Auto-failed %d stale ingestion job(s) that exceeded the %s threshold",
                stale_result.rowcount,
                _STALE_JOB_THRESHOLD,
            )

        # --- Check for genuinely running jobs --------------------------------
        running = await self._db.execute(
            select(IngestionJob).where(IngestionJob.status.in_(active_statuses))
        )
        if running.scalar_one_or_none() is not None:
            raise IngestionAlreadyRunningError()

        # Resolve folder ID (drive-specific: request > AppConfig > env > None)
        folder_id = request.folder_id
        if request.source == "google_drive":
            saved_default = await self._get_config(_CFG_DRIVE_FOLDER_ID)
            settings = get_settings()
            folder_id = (
                request.folder_id or saved_default or settings.google_drive_folder_id or None
            )

        # Create job
        job = IngestionJob(
            triggered_by=admin_user_id,
            source=request.source,
            folder_id=folder_id,
            status=IngestionStatus.PENDING,
        )
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)

        logger.info("Ingestion job created: %s", job.id)

        # Dispatch to Celery worker (non-blocking)
        from app.domain.ingestion.tasks import run_ingestion_task

        run_ingestion_task.delay(
            job_id=str(job.id),
            admin_user_id=str(admin_user_id),
            force=request.force,
            source=request.source,
        )
        logger.info("Ingestion job %s dispatched to Celery worker", job.id)

        return IngestionJobResponse.model_validate(job)

    async def retry_job(
        self,
        job_id: uuid.UUID,
        admin_user_id: uuid.UUID,
    ) -> IngestionJobResponse:
        """Retry a failed or cancelled job by resuming from where it left off.

        Resets failed/pending IndexedFile rows back to PENDING so the pipeline
        re-processes only the files that didn't complete. Reuses the same
        IngestionJob record (same folder/source).

        Raises:
            IngestionJobNotFoundError: If job not found
            IngestionAlreadyRunningError: If another job is already active
            IngestionError: If job is not in a retryable state
        """
        from app.domain.ingestion.exceptions import IngestionError
        from app.domain.ingestion.models import IndexedFile, IndexedFileStage, IndexedFileStatus

        result = await self._db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        original = result.scalar_one_or_none()
        if original is None:
            raise IngestionJobNotFoundError(str(job_id))

        if original.status not in (IngestionStatus.FAILED, IngestionStatus.CANCELLED):
            raise IngestionError(
                f"Only failed or cancelled jobs can be retried (current: {original.status.value})"
            )

        # Block if another job is already running
        active_statuses = [
            IngestionStatus.PENDING,
            IngestionStatus.SCANNING,
            IngestionStatus.PROCESSING,
        ]
        running = await self._db.execute(
            select(IngestionJob).where(
                IngestionJob.status.in_(active_statuses),
                IngestionJob.id != job_id,
            )
        )
        if running.scalar_one_or_none() is not None:
            raise IngestionAlreadyRunningError()

        # Count retryable files
        retryable_statuses = [
            IndexedFileStatus.FAILED.value,
            IndexedFileStatus.PENDING.value,
            IndexedFileStatus.PROCESSING.value,
        ]
        retryable_count_result = await self._db.execute(
            select(func.count())
            .select_from(IndexedFile)
            .where(
                IndexedFile.job_id == job_id,
                IndexedFile.status.in_(retryable_statuses),
            )
        )
        retryable_count = retryable_count_result.scalar() or 0

        if retryable_count == 0:
            raise IngestionError("No retryable files found in this job")

        # Reset retryable IndexedFile rows back to PENDING
        await self._db.execute(
            sa_update(IndexedFile)
            .where(
                IndexedFile.job_id == job_id,
                IndexedFile.status.in_(retryable_statuses),
            )
            .values(
                status=IndexedFileStatus.PENDING.value,
                stage=IndexedFileStage.PENDING.value,
                error_message=None,
                processed_at=None,
            )
            .execution_options(synchronize_session=False)
        )

        # Reset the job to PROCESSING (scanning phase already complete)
        await self._db.execute(
            sa_update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status=IngestionStatus.PROCESSING,
                error_message=None,
                completed_at=None,
                failed_files=0,
            )
            .execution_options(synchronize_session=False)
        )
        await self._db.commit()

        # Refresh the job
        self._db.expire_all()
        result = await self._db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one()

        logger.info("Retrying ingestion job %s (%d files to reprocess)", job_id, retryable_count)

        # Dispatch to Celery worker (skip scanning, process only)
        from app.domain.ingestion.tasks import run_ingestion_task

        run_ingestion_task.delay(
            job_id=str(job_id),
            admin_user_id=str(admin_user_id),
            source=job.source,
            retry=True,
        )

        return IngestionJobResponse.model_validate(job)

    async def get_job(self, job_id: uuid.UUID) -> IngestionJobResponse:
        """Get an ingestion job by ID.

        Raises:
            IngestionJobNotFoundError: If job not found
        """
        result = await self._db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise IngestionJobNotFoundError(str(job_id))

        return IngestionJobResponse.model_validate(job)

    async def get_stats(self) -> IngestionStatsResponse:
        """Get aggregate ingestion statistics.

        Returns counts by status, totals for files processed/failed/skipped,
        and info about the most recent active job.
        """
        # Count by status
        status_counts_result = await self._db.execute(
            select(IngestionJob.status, func.count().label("cnt")).group_by(IngestionJob.status)
        )
        status_counts: dict[str, int] = {row.status.value: row.cnt for row in status_counts_result}

        # Total files across all completed jobs
        totals_result = await self._db.execute(
            select(
                func.sum(IngestionJob.processed_files).label("total_processed"),
                func.sum(IngestionJob.failed_files).label("total_failed"),
                func.sum(IngestionJob.skipped_files).label("total_skipped"),
                func.count().label("total_jobs"),
            )
        )
        totals = totals_result.one()

        # Active job (most recent non-terminal)
        active_result = await self._db.execute(
            select(IngestionJob)
            .where(
                IngestionJob.status.in_(
                    [
                        IngestionStatus.PENDING,
                        IngestionStatus.SCANNING,
                        IngestionStatus.PROCESSING,
                    ]
                )
            )
            .order_by(IngestionJob.started_at.desc())
            .limit(1)
        )
        active_job = active_result.scalar_one_or_none()

        return IngestionStatsResponse(
            total_jobs=totals.total_jobs or 0,
            jobs_by_status=status_counts,
            total_files_processed=totals.total_processed or 0,
            total_files_failed=totals.total_failed or 0,
            total_files_skipped=totals.total_skipped or 0,
            active_job=IngestionJobResponse.model_validate(active_job) if active_job else None,
        )

    async def list_jobs(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> IngestionJobListResponse:
        """List ingestion jobs with pagination."""
        offset = (page - 1) * page_size

        count_result = await self._db.execute(select(func.count()).select_from(IngestionJob))
        total = count_result.scalar() or 0

        result = await self._db.execute(
            select(IngestionJob)
            .order_by(IngestionJob.started_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        jobs = result.scalars().all()

        return IngestionJobListResponse(
            items=[IngestionJobResponse.model_validate(j) for j in jobs],
            total=total,
        )

    async def cancel_job(self, job_id: uuid.UUID) -> IngestionJobResponse:
        """Cancel a running ingestion job.

        Uses a direct SQL UPDATE (same pattern as the orchestrator) to ensure
        the write persists even when the Celery worker is concurrently updating
        the same row via its own SQL UPDATEs.

        Raises:
            IngestionJobNotFoundError: If job not found
        """
        result = await self._db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise IngestionJobNotFoundError(str(job_id))

        if job.status in (
            IngestionStatus.PENDING,
            IngestionStatus.SCANNING,
            IngestionStatus.PROCESSING,
        ):
            now = datetime.now(UTC)
            stmt = (
                sa_update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    status=IngestionStatus.CANCELLED,
                    completed_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            await self._db.execute(stmt)
            await self._db.commit()

            # Keep the in-memory object in sync for the response
            job.status = IngestionStatus.CANCELLED
            job.completed_at = now
            logger.info("Ingestion job cancelled: %s", job.id)

        return IngestionJobResponse.model_validate(job)

    # ------------------------------------------------------------------
    # Drive folder browsing & default folder
    # ------------------------------------------------------------------

    async def browse_drive_folders(
        self,
        parent_id: str = "root",
        user_id: uuid.UUID | None = None,
    ) -> list[DriveFolderEntry]:
        """List subfolders of a Drive folder (no files).

        When ``user_id`` is provided the user's stored OAuth tokens are used
        so they browse their own Drive.  Falls back to server-level
        credentials (service account / env OAuth) when no per-user tokens
        are available.
        """

        connector = await self._get_drive_connector(user_id)
        entries = await connector.list_folder_children(parent_id)
        return [e for e in entries if e.is_folder]

    async def _get_drive_connector(
        self,
        user_id: uuid.UUID | None = None,
    ) -> GoogleDriveConnector:
        """Build an authenticated GoogleDriveConnector.

        Tries the logged-in user's stored OAuth tokens first, then falls
        back to server-level credentials.
        """
        from app.domain.auth.models import OAuthAccount
        from app.domain.ingestion.drive_connector import GoogleDriveConnector
        from app.infra.encryption import decrypt_value

        # --- Try per-user OAuth tokens ---
        if user_id is not None:
            result = await self._db.execute(
                select(OAuthAccount).where(
                    OAuthAccount.user_id == user_id,
                    OAuthAccount.provider == "google",
                )
            )
            account = result.scalar_one_or_none()
            if account and account.access_token_enc:
                access_token = decrypt_value(account.access_token_enc)
                refresh_token = (
                    decrypt_value(account.refresh_token_enc) if account.refresh_token_enc else None
                )
                connector = GoogleDriveConnector.from_user_tokens(
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
                # Persist refreshed tokens if google-auth auto-refreshed them
                await self._maybe_persist_refreshed_token(account, connector)
                return connector

        # --- Fallback: server-level credentials ---
        connector = GoogleDriveConnector()
        await connector.authenticate()
        return connector

    async def _maybe_persist_refreshed_token(
        self,
        account: OAuthAccount,
        connector: GoogleDriveConnector,
    ) -> None:
        """If the google-auth library refreshed the access token, persist it."""
        from app.infra.encryption import decrypt_value, encrypt_value

        creds = connector._credentials
        if creds is None or not creds.token:
            return
        # Compare decrypted stored token against current token
        # (Fernet uses a random IV, so re-encrypting always produces a different ciphertext)
        stored_token = decrypt_value(account.access_token_enc)
        if creds.token != stored_token:
            account.access_token_enc = encrypt_value(creds.token)
            if creds.expiry:
                account.token_expiry = creds.expiry
            await self._db.commit()

    async def get_default_folder(self) -> DefaultFolderResponse:
        """Get the saved default Drive folder."""
        folder_id = await self._get_config(_CFG_DRIVE_FOLDER_ID)
        folder_name = await self._get_config(_CFG_DRIVE_FOLDER_NAME)
        return DefaultFolderResponse(folder_id=folder_id, folder_name=folder_name)

    async def save_default_folder(self, folder_id: str, folder_name: str) -> DefaultFolderResponse:
        """Save/update the default Drive folder."""
        await self._set_config(_CFG_DRIVE_FOLDER_ID, folder_id)
        await self._set_config(_CFG_DRIVE_FOLDER_NAME, folder_name)
        await self._db.commit()
        return DefaultFolderResponse(folder_id=folder_id, folder_name=folder_name)

    # ------------------------------------------------------------------
    # AppConfig helpers
    # ------------------------------------------------------------------

    async def _get_config(self, key: str) -> str | None:
        result = await self._db.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def _set_config(self, key: str, value: str) -> None:
        result = await self._db.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            self._db.add(AppConfig(key=key, value=value))
