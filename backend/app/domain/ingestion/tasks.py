"""Celery tasks for Google Drive ingestion.

The IngestionOrchestrator runs a two-phase pipeline: Phase 1 (scanner)
does a deterministic BFS of the Drive folder tree and indexes all files;
Phase 2 (processor) ingests each indexed file sequentially. It runs
inside this Celery task via asyncio.run() in a thread (-P threads).

No auto-retry: the orchestrator manages its own internal error handling
and progress tracking (status field on IngestionJob). A crashed task
is redelivered once by Celery (acks_late=True). Re-running after that
must be triggered manually by the admin.

IMPORTANT — event loop isolation:
Each Celery thread task calls asyncio.run(), which creates a brand-new
event loop. The global _session_factory holds asyncpg connections bound
to the event loop from the API server process. Those connections cannot
be used from a different loop (raises "Future attached to a different loop").
We therefore build a fresh async engine + session factory per task
invocation, scoped to the task's own event loop, and dispose it on exit.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.infra.llm import llm_provider
from app.infra.storage import storage_client

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.domain.ingestion.tasks.run_ingestion_task",
    bind=True,
    max_retries=0,   # No auto-retry — orchestrator handles its own failure state
    acks_late=False,  # Acknowledge IMMEDIATELY so OOM kills don't requeue the task
    time_limit=7200,       # 2-hour hard kill for runaway jobs
    soft_time_limit=6900,  # 115-min soft limit (raises SoftTimeLimitExceeded first)
    rate_limit="1/m",      # Only 1 ingestion task per minute — prevents concurrent runs
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
    from app.domain.ingestion.orchestrator import IngestionOrchestrator

    job_uuid = uuid.UUID(job_id)
    admin_uuid = uuid.UUID(admin_user_id)

    async def _run() -> None:
        import app.infra.database as _db_module
        from app.infra.database import build_session_factory
        from sqlalchemy import update as sa_update

        if _db_module._engine is None:
            logger.error("Database not initialised before ingestion task")
            return

        # Build a fresh engine + session factory bound to THIS event loop.
        # The global _engine/_session_factory is bound to the API server's
        # event loop and cannot be safely used from a different asyncio.run().
        task_engine, task_session_factory = build_session_factory(_db_module._engine.url)

        try:
            async with task_session_factory() as db:
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
                    session_factory=task_session_factory,
                )

                try:
                    await orchestrator.run(job=job, admin_user_id=admin_uuid, force=force)
                    logger.info("Ingestion job completed: %s", job_uuid)
                except Exception:
                    logger.exception("Ingestion job failed: %s", job_uuid)
                    # Guarantee the job is marked FAILED so it never stays
                    # stuck in PENDING/SCANNING/PROCESSING as a zombie.
                    # The orchestrator's own except handler may have already
                    # done this, but if that handler itself failed (e.g. DB
                    # session was broken), we need a last-resort fallback
                    # using a fresh session.
                    try:
                        async with task_session_factory() as fallback_db:
                            stmt = (
                                sa_update(IngestionJob)
                                .where(
                                    IngestionJob.id == job_uuid,
                                    IngestionJob.status.in_([
                                        IngestionStatus.PENDING,
                                        IngestionStatus.SCANNING,
                                        IngestionStatus.PROCESSING,
                                    ]),
                                )
                                .values(
                                    status=IngestionStatus.FAILED,
                                    error_message="Task crashed unexpectedly",
                                    completed_at=datetime.now(timezone.utc),
                                )
                                .execution_options(synchronize_session=False)
                            )
                            await fallback_db.execute(stmt)
                            await fallback_db.commit()
                            logger.info(
                                "Fallback: marked job %s as FAILED", job_uuid,
                            )
                    except Exception:
                        logger.exception(
                            "Fallback FAILED status write also failed for job %s — "
                            "job may be stuck. trigger_ingestion stale-job detection "
                            "will clean it up.",
                            job_uuid,
                        )
        finally:
            await task_engine.dispose()

    asyncio.run(_run())
