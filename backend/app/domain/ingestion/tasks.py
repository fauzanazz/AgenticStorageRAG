"""Celery tasks for Google Drive ingestion.

The IngestionOrchestrator is a long-running ReAct agent (up to 500
iterations). It runs inside this Celery task, which executes in a
thread (-P threads). Each iteration: LLM call → Drive I/O (non-blocking
via asyncio.to_thread) → DB write.

No auto-retry: the orchestrator manages its own internal error handling
and progress tracking (status field on IngestionJob). A crashed task
is redelivered once by Celery (acks_late=True). Re-running after that
must be triggered manually by the admin.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.celery_app import celery_app
from app.infra.database import _session_factory
from app.infra.llm import llm_provider
from app.infra.storage import storage_client

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.domain.ingestion.tasks.run_ingestion_task",
    bind=True,
    max_retries=0,   # No auto-retry — orchestrator handles its own failure state
    acks_late=True,
    time_limit=7200,       # 2-hour hard kill for runaway jobs
    soft_time_limit=6900,  # 115-min soft limit (raises SoftTimeLimitExceeded first)
)
def run_ingestion_task(  # type: ignore[misc]
    self,
    *,
    job_id: str,
    admin_user_id: str,
    force: bool = False,
) -> None:
    """Run the IngestionOrchestrator for a triggered Google Drive ingestion job.

    Args:
        job_id: UUID string of the IngestionJob record.
        admin_user_id: UUID string of the admin who triggered the job.
        force: Re-ingest already-processed files when True.
    """
    from app.domain.ingestion.drive_connector import GoogleDriveConnector
    from app.domain.ingestion.models import IngestionJob
    from app.domain.ingestion.orchestrator import IngestionOrchestrator

    job_uuid = uuid.UUID(job_id)
    admin_uuid = uuid.UUID(admin_user_id)

    async def _run() -> None:
        if _session_factory is None:
            logger.error("Database not initialised before ingestion task")
            return

        async with _session_factory() as db:
            job = await db.get(IngestionJob, job_uuid)
            if job is None:
                logger.error("Ingestion job not found: %s", job_uuid)
                return

            connector = GoogleDriveConnector()
            orchestrator = IngestionOrchestrator(
                db=db,
                storage=storage_client,
                connector=connector,
                llm=llm_provider,
            )

            try:
                await orchestrator.run(job=job, admin_user_id=admin_uuid, force=force)
                logger.info("Ingestion job completed: %s", job_uuid)
            except Exception:
                logger.exception("Ingestion job failed: %s", job_uuid)
                raise  # Let Celery record the failure; acks_late ensures redelivery

    asyncio.run(_run())
