"""Ingestion service.

Coordinates ingestion jobs, providing the business logic layer
between the router and the swarm/connectors.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import (
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionStatsResponse,
    TriggerIngestionRequest,
)
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)


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

        Args:
            request: Ingestion trigger parameters
            admin_user_id: Admin user who triggered the job

        Returns:
            The created IngestionJob response

        Raises:
            IngestionAlreadyRunningError: If a job is already active
        """
        # Check for running jobs
        running = await self._db.execute(
            select(IngestionJob).where(
                IngestionJob.status.in_([
                    IngestionStatus.PENDING,
                    IngestionStatus.SCANNING,
                    IngestionStatus.PROCESSING,
                ])
            )
        )
        if running.scalar_one_or_none() is not None:
            raise IngestionAlreadyRunningError()

        # Resolve folder ID: request > config > None (root)
        settings = get_settings()
        folder_id = request.folder_id or settings.google_drive_folder_id or None

        # Create job
        job = IngestionJob(
            triggered_by=admin_user_id,
            source="google_drive",
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
        )
        logger.info("Ingestion job %s dispatched to Celery worker", job.id)

        return IngestionJobResponse.model_validate(job)

    async def get_job(self, job_id: uuid.UUID) -> IngestionJobResponse:
        """Get an ingestion job by ID.

        Raises:
            IngestionJobNotFoundError: If job not found
        """
        result = await self._db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        )
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
            select(IngestionJob.status, func.count().label("cnt"))
            .group_by(IngestionJob.status)
        )
        status_counts: dict[str, int] = {
            row.status.value: row.cnt for row in status_counts_result
        }

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
                IngestionJob.status.in_([
                    IngestionStatus.PENDING,
                    IngestionStatus.SCANNING,
                    IngestionStatus.PROCESSING,
                ])
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

        count_result = await self._db.execute(
            select(func.count()).select_from(IngestionJob)
        )
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

        Raises:
            IngestionJobNotFoundError: If job not found
        """
        result = await self._db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise IngestionJobNotFoundError(str(job_id))

        if job.status in (IngestionStatus.PENDING, IngestionStatus.SCANNING, IngestionStatus.PROCESSING):
            job.status = IngestionStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)
            await self._db.commit()
            logger.info("Ingestion job cancelled: %s", job.id)

        return IngestionJobResponse.model_validate(job)
