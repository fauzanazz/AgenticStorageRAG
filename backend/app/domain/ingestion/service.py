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

from app.domain.ingestion.drive_connector import GoogleDriveConnector
from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import (
    IngestionJobListResponse,
    IngestionJobResponse,
    TriggerIngestionRequest,
)
from app.domain.ingestion.swarm import IngestionSwarm
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

        # Create job
        job = IngestionJob(
            triggered_by=admin_user_id,
            source="google_drive",
            folder_id=request.folder_id,
            status=IngestionStatus.PENDING,
        )
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)

        logger.info("Ingestion job created: %s", job.id)

        # Run the swarm (async, non-blocking in background)
        connector = GoogleDriveConnector()
        swarm = IngestionSwarm(
            db=self._db,
            storage=self._storage,
            connector=connector,
        )

        # Execute synchronously for now (background worker handles async)
        try:
            await swarm.run(
                job=job,
                admin_user_id=admin_user_id,
                force=request.force,
            )
        except Exception as e:
            logger.exception("Ingestion job %s failed: %s", job.id, e)
            # Job status already updated by swarm

        # Refresh to get final state
        await self._db.refresh(job)
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
