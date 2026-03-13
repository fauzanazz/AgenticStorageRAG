"""Background job worker.

Processes queued jobs from Redis. Runs as a separate process
alongside the API server (two-process modular monolith).

Usage:
    python -m app.infra.worker

Job types are registered via the HANDLERS dict. Each handler is
an async function that receives the job payload dict.
"""

from __future__ import annotations

import asyncio
import logging
import signal
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


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register a handler for a specific job type.

    Args:
        job_type: The job type string (e.g., "process_document", "extract_kg")
        handler: Async function that processes the job payload
    """
    HANDLERS[job_type] = handler
    logger.info("Registered job handler: %s", job_type)


async def process_job(job_data: dict[str, Any]) -> None:
    """Process a single job by dispatching to the registered handler.

    Args:
        job_data: Job payload. Must contain a "type" key.
    """
    job_type = job_data.get("type")
    if not job_type:
        logger.error("Job missing 'type' field: %s", job_data)
        return

    handler = HANDLERS.get(job_type)
    if handler is None:
        logger.error("No handler registered for job type: %s", job_type)
        return

    try:
        logger.info("Processing job: %s (id: %s)", job_type, job_data.get("id", "unknown"))
        await handler(job_data)
        logger.info("Job completed: %s (id: %s)", job_type, job_data.get("id", "unknown"))
    except Exception:
        logger.exception("Job failed: %s (id: %s)", job_type, job_data.get("id", "unknown"))
        # TODO: Implement retry logic with exponential backoff
        # TODO: Move to dead letter queue after max retries


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    """Main worker loop. Polls all queues for jobs.

    Args:
        shutdown_event: Event that signals graceful shutdown.
    """
    logger.info("Worker started. Listening on queues: %s", ALL_QUEUES)

    while not shutdown_event.is_set():
        for queue_name in ALL_QUEUES:
            try:
                job_data = await redis_client.dequeue(queue_name, timeout=1)
                if job_data is not None:
                    await process_job(job_data)
            except Exception:
                logger.exception("Error polling queue %s", queue_name)
                await asyncio.sleep(1)

    logger.info("Worker shutting down gracefully")


async def run_worker() -> None:
    """Entry point for the worker process."""
    # Connect to Redis
    await redis_client.connect()

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


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
