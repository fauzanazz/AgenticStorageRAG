"""Celery application factory.

This module creates the Celery app singleton used by:
  - The worker process: celery -A app.celery_app worker
  - Domain task modules: importing celery_app to register tasks with @celery_app.task

Queue layout (all on Redis DB 1 to keep Celery keys separate from the
app cache which lives on DB 0):
  documents  — document processing jobs
  ingestion  — Google Drive ingestion jobs
  knowledge  — KG extraction jobs (reserved for future use)

Retry policy is defined per-task via autoretry_for / max_retries /
default_retry_delay in the task decorator — not centrally here.

Worker startup:
    celery -A app.celery_app worker \\
        --loglevel=info \\
        --concurrency=4 \\
        -P threads \\
        -Q documents,ingestion,knowledge
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_ready

from app.config import get_settings

logger = logging.getLogger(__name__)


def _broker_url() -> str:
    """Build the Celery broker URL from settings.

    Uses Redis DB 1 to keep Celery keys separate from the app cache
    (DB 0). The REDIS_URL in settings targets DB 0 (e.g.
    redis://redis:6379/0); we replace the trailing index with 1.
    """
    url = str(get_settings().redis_url)
    # Replace database index: strip trailing /N and append /1
    if "/" in url.rsplit("://", 1)[-1]:
        base = url.rsplit("/", 1)[0]
        return f"{base}/1"
    return f"{url}/1"


def create_celery_app() -> Celery:
    app = Celery("dingdong_rag")

    broker = _broker_url()

    app.conf.update(
        broker_url=broker,
        result_backend=broker,

        # Route tasks to dedicated queues by module prefix
        task_routes={
            "app.domain.documents.tasks.*": {"queue": "documents"},
            "app.domain.ingestion.tasks.*": {"queue": "ingestion"},
            "app.domain.knowledge.tasks.*": {"queue": "knowledge"},
        },

        # Acknowledge task only after it completes (at-least-once delivery)
        task_acks_late=True,
        # Reject and requeue on worker crash (SIGKILL / OOM)
        task_reject_on_worker_lost=True,

        # Serialisation
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,

        # Autodiscover tasks from domain task modules
        imports=[
            "app.domain.documents.tasks",
            "app.domain.ingestion.tasks",
        ],
    )

    return app


celery_app = create_celery_app()


@worker_ready.connect
def _init_worker_resources(**kwargs: object) -> None:
    """Initialise shared resources once when the worker is ready to accept tasks.

    ``worker_ready`` fires in the main process after the worker has fully
    started, regardless of pool type. This is the correct signal for
    ``--pool=threads`` because ``worker_process_init`` only fires on
    *forked* child processes — with threads there are no forks, so that
    signal never runs.
    """
    from app.infra.database import init_db
    from app.infra.llm import llm_provider
    from app.infra.storage import storage_client

    init_db()
    storage_client.connect()
    llm_provider.initialize()

    logger.info("Worker process resources initialised")
