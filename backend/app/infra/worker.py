"""Background job worker.

Processes queued jobs from Redis. Runs as a separate process
alongside the API server (two-process modular monolith).

Usage:
    python -m app.infra.worker

Job types are registered via the HANDLERS dict. Each handler is
an async function that receives the job payload dict.

Retry policy:
    Failed jobs are retried with exponential backoff (2s, 4s, 8s).
    After MAX_RETRIES failures, jobs are moved to a dead-letter queue
    (dlq:<queue_name>) for manual inspection.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from app.infra.redis_client import redis_client

logger = logging.getLogger(__name__)

# Type alias for job handlers
JobHandler = Callable[[dict[str, Any]], Awaitable[None]]

# Registry of job type -> handler function
# Domains register their handlers here during initialization
HANDLERS: dict[str, JobHandler] = {}

# Queue names
QUEUE_DOCUMENTS = "jobs:documents"
QUEUE_KNOWLEDGE = "jobs:knowledge"
QUEUE_INGESTION = "jobs:ingestion"

# All queues the worker listens to
ALL_QUEUES = [QUEUE_DOCUMENTS, QUEUE_KNOWLEDGE, QUEUE_INGESTION]

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 2  # Exponential backoff: 2s, 4s, 8s


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register a handler for a specific job type.

    Args:
        job_type: The job type string (e.g., "process_document", "extract_kg")
        handler: Async function that processes the job payload
    """
    HANDLERS[job_type] = handler
    logger.info("Registered job handler: %s", job_type)


async def process_job(job_data: dict[str, Any], queue_name: str) -> None:
    """Process a single job by dispatching to the registered handler.

    On failure, retries with exponential backoff up to MAX_RETRIES times.
    After max retries, moves the job to the dead-letter queue.

    Args:
        job_data: Job payload. Must contain a "type" key.
        queue_name: The queue this job was dequeued from (for re-enqueue on retry).
    """
    job_type = job_data.get("type")
    if not job_type:
        logger.error("Job missing 'type' field: %s", job_data)
        return

    handler = HANDLERS.get(job_type)
    if handler is None:
        logger.error("No handler registered for job type: %s", job_type)
        # Move unhandled job types to DLQ immediately
        job_data["_dlq_reason"] = f"No handler registered for type: {job_type}"
        job_data["_dlq_at"] = datetime.now(timezone.utc).isoformat()
        await redis_client.move_to_dlq(queue_name, job_data)
        return

    job_id = job_data.get("id", "unknown")
    retry_count = job_data.get("_retry_count", 0)

    try:
        logger.info(
            "Processing job: %s (id: %s, attempt: %d/%d)",
            job_type, job_id, retry_count + 1, MAX_RETRIES + 1,
        )
        await handler(job_data)
        logger.info("Job completed: %s (id: %s)", job_type, job_id)

    except Exception as exc:
        logger.exception(
            "Job failed: %s (id: %s, attempt: %d/%d)",
            job_type, job_id, retry_count + 1, MAX_RETRIES + 1,
        )

        if retry_count < MAX_RETRIES:
            # Retry with exponential backoff
            delay = BASE_DELAY_SECONDS * (2 ** retry_count)
            logger.info(
                "Retrying job %s (id: %s) in %ds (attempt %d/%d)",
                job_type, job_id, delay, retry_count + 2, MAX_RETRIES + 1,
            )
            await asyncio.sleep(delay)

            # Re-enqueue with incremented retry count
            job_data["_retry_count"] = retry_count + 1
            job_data["_last_error"] = str(exc)[:500]
            job_data["_last_retry_at"] = datetime.now(timezone.utc).isoformat()
            await redis_client.enqueue(queue_name, job_data)
        else:
            # Max retries exceeded — move to dead-letter queue
            logger.error(
                "Job exhausted retries: %s (id: %s). Moving to DLQ.",
                job_type, job_id,
            )
            job_data["_dlq_reason"] = f"Max retries ({MAX_RETRIES}) exceeded"
            job_data["_last_error"] = str(exc)[:500]
            job_data["_dlq_at"] = datetime.now(timezone.utc).isoformat()
            await redis_client.move_to_dlq(queue_name, job_data)


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    """Main worker loop. Polls all queues for jobs.

    Args:
        shutdown_event: Event that signals graceful shutdown.
    """
    logger.info("Worker started. Listening on queues: %s", ALL_QUEUES)
    logger.info("Retry policy: max_retries=%d, base_delay=%ds", MAX_RETRIES, BASE_DELAY_SECONDS)

    while not shutdown_event.is_set():
        for queue_name in ALL_QUEUES:
            try:
                job_data = await redis_client.dequeue(queue_name, timeout=1)
                if job_data is not None:
                    await process_job(job_data, queue_name)
            except Exception:
                logger.exception("Error polling queue %s", queue_name)
                await asyncio.sleep(1)

    logger.info("Worker shutting down gracefully")


async def run_worker() -> None:
    """Entry point for the worker process.

    Connects to Redis and database, registers all domain job handlers,
    then starts the worker loop.
    """
    # Initialize database (required for job handlers that access DB)
    from app.infra.database import init_db, close_db
    init_db()

    # Import all ORM models so SQLAlchemy metadata resolves foreign keys
    import app.domain.auth.models  # noqa: F401 (users table)
    import app.domain.documents.models  # noqa: F401 (documents, chunks tables)
    import app.domain.agents.models  # noqa: F401 (conversations, messages tables)
    import app.domain.ingestion.models  # noqa: F401 (ingestion_jobs table)

    logger.info("Database initialized")

    # Connect to Redis
    await redis_client.connect()

    # Initialize storage client (required for ingestion jobs)
    from app.infra.storage import storage_client
    storage_client.connect()
    logger.info("Storage client initialized")

    # Initialize LLM provider (required for orchestrator agent)
    from app.infra.llm import llm_provider
    llm_provider.initialize()
    logger.info("LLM provider initialized")

    # Register domain job handlers
    from app.domain.documents.jobs import register_document_handlers
    register_document_handlers()

    from app.domain.ingestion.jobs import register_ingestion_handlers
    register_ingestion_handlers()

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await worker_loop(shutdown_event)
    finally:
        await redis_client.close()
        await close_db()
        logger.info("Worker resources cleaned up")


def main() -> None:
    """CLI entry point."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Fix the Python -m dual-module problem:
    # When running `python -m app.infra.worker`, this file is loaded as both
    # `__main__` and `app.infra.worker` (separate module instances).
    # Handlers registered via `from app.infra.worker import register_handler`
    # write to `app.infra.worker.HANDLERS`, but process_job() runs in
    # `__main__` which has its own empty HANDLERS dict.
    # Solution: alias __main__ to app.infra.worker so they share the same dict.
    if __name__ == "__main__" and "app.infra.worker" not in sys.modules:
        sys.modules["app.infra.worker"] = sys.modules["__main__"]

    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
