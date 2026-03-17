"""Background job handler for ingestion processing.

Registered with the worker to handle 'run_ingestion' jobs.
The orchestrator agent runs inside the worker process, not inline
in the HTTP request.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.domain.ingestion.drive_connector import GoogleDriveConnector
from app.domain.ingestion.models import IngestionJob
from app.domain.ingestion.orchestrator import IngestionOrchestrator
from app.infra.database import _session_factory
from app.infra.llm import llm_provider
from app.infra.storage import storage_client
from app.infra.worker import register_handler

logger = logging.getLogger(__name__)


async def handle_run_ingestion(job_data: dict[str, Any]) -> None:
    """Handle an ingestion job dispatched from the API.

    Called by the worker process when a 'run_ingestion' job is dequeued.
    The orchestrator agent runs here (in the worker), keeping the API
    request non-blocking.

    Each status update uses its own short-lived session to avoid
    pgbouncer transaction-mode connection reuse issues.

    Args:
        job_data: Must contain 'job_id', 'admin_user_id', and 'force' keys.
    """
    job_id_str = job_data.get("job_id")
    admin_user_id_str = job_data.get("admin_user_id")
    force = job_data.get("force", False)

    if not job_id_str or not admin_user_id_str:
        logger.error("run_ingestion job missing required fields: %s", job_data)
        return

    job_id = uuid.UUID(job_id_str)
    admin_user_id = uuid.UUID(admin_user_id_str)

    if _session_factory is None:
        logger.error("Database not initialized")
        return

    # Use a fresh session for the entire orchestrator run.
    # The orchestrator will commit inside this session for each per-file update.
    async with _session_factory() as db:
        # Load the job from DB
        job = await db.get(IngestionJob, job_id)
        if job is None:
            logger.error("Ingestion job not found: %s", job_id)
            return

        connector = GoogleDriveConnector()
        orchestrator = IngestionOrchestrator(
            db=db,
            storage=storage_client,
            connector=connector,
            llm=llm_provider,
        )

        try:
            await orchestrator.run(
                job=job,
                admin_user_id=admin_user_id,
                force=force,
            )
            logger.info("Ingestion job completed: %s", job_id)
        except Exception:
            logger.exception("Ingestion job failed: %s", job_id)
            # Job status already updated to FAILED by orchestrator


def register_ingestion_handlers() -> None:
    """Register all ingestion-related job handlers with the worker."""
    register_handler("run_ingestion", handle_run_ingestion)
    logger.info("Ingestion job handlers registered")
