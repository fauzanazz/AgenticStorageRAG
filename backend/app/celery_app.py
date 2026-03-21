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

import gc
import logging
import resource
import sys
import threading
import tracemalloc

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

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

        # Only prefetch 1 task per thread — prevents the worker from grabbing
        # multiple ingestion tasks and running them concurrently, which causes
        # OOM when 4 IngestionOrchestrators run in parallel.
        worker_prefetch_multiplier=1,

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

_heartbeat_stop = threading.Event()

HEARTBEAT_INTERVAL_SECONDS = 30
MEMORY_SNAPSHOT_EVERY = 10  # detailed snapshot every 10th heartbeat (~5 min)


def _get_rss_mb() -> float:
    """Current process RSS in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports ru_maxrss in bytes, Linux in KB
    if sys.platform == "darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


def _log_memory_snapshot() -> None:
    """Log tracemalloc top allocations. Lightweight — no gc object scan."""
    snapshot = tracemalloc.take_snapshot()
    snapshot = snapshot.filter_traces([
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
        tracemalloc.Filter(False, tracemalloc.__file__),
    ])
    top = snapshot.statistics("lineno")
    logger.info("── tracemalloc top 10 ──")
    for stat in top[:10]:
        logger.info("  %s", stat)

    # Lightweight: just gc stats, no object iteration
    counts = gc.get_count()
    collected = gc.collect()
    logger.info(
        "── gc: gen0=%d gen1=%d gen2=%d | collected %d ──",
        counts[0], counts[1], counts[2], collected,
    )


def _heartbeat_loop() -> None:
    """Log a heartbeat line every HEARTBEAT_INTERVAL_SECONDS."""
    tick = 0
    while not _heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        tick += 1
        rss = _get_rss_mb()
        active = threading.active_count()
        logger.info("♥ worker alive | RSS %.0f MB | %d active threads", rss, active)

        if tick % MEMORY_SNAPSHOT_EVERY == 0:
            try:
                _log_memory_snapshot()
            except Exception:
                logger.exception("Memory snapshot failed")


@worker_shutdown.connect
def _stop_heartbeat(**kwargs: object) -> None:
    _heartbeat_stop.set()


@worker_ready.connect
def _init_worker_resources(**kwargs: object) -> None:
    """Initialise shared resources once when the worker is ready to accept tasks.

    ``worker_ready`` fires in the main process after the worker has fully
    started, regardless of pool type. This is the correct signal for
    ``--pool=threads`` because ``worker_process_init`` only fires on
    *forked* child processes — with threads there are no forks, so that
    signal never runs.
    """
    import asyncio

    # Start tracemalloc early to capture allocations from init onward
    tracemalloc.start(5)  # 5 frames — enough to identify call sites

    from app.infra.database import init_db
    from app.infra.llm import llm_provider
    from app.infra.neo4j_client import neo4j_client
    from app.infra.storage import storage_client

    # Register ALL domain models with Base.metadata before init_db() creates the
    # engine. SQLAlchemy resolves cross-domain FK strings (e.g.
    # IngestionJob.triggered_by → "users.id") by scanning Base.metadata at mapper
    # configuration time. Without these imports the worker's metadata is incomplete
    # and raises NoReferencedTableError on the first DB query.
    import app.domain.auth.models          # noqa: F401
    import app.domain.documents.models     # noqa: F401
    import app.domain.knowledge.models     # noqa: F401
    import app.domain.agents.models        # noqa: F401
    import app.domain.ingestion.models     # noqa: F401
    import app.domain.settings.models      # noqa: F401

    init_db()
    storage_client.connect()
    llm_provider.initialize()

    # Neo4j connect() is async — run it in a one-shot event loop.
    # The async driver manages its own connection pool internally and is
    # safe to use from the per-task asyncio.run() loops that threads create.
    try:
        asyncio.run(neo4j_client.connect())
    except Exception as exc:
        logger.warning("Neo4j connection failed during worker init (non-fatal): %s", exc)

    # Fail any ingestion jobs that were left in an active state by a previous
    # worker process (e.g. container restart killed a running task).  Without
    # this, zombie jobs block the UI and prevent new triggers until someone
    # manually cleans them up or the stale-job detector runs on the next
    # trigger_ingestion() call.
    try:
        asyncio.run(_fail_zombie_ingestion_jobs())
    except Exception as exc:
        logger.warning("Zombie job cleanup failed (non-fatal): %s", exc)

    # Start heartbeat so tmux/logs show the worker is alive
    t = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    t.start()

    logger.info("Worker process resources initialised")


async def _fail_zombie_ingestion_jobs() -> None:
    """Mark any active ingestion jobs as FAILED on worker startup.

    When the worker container restarts, any in-flight Celery tasks are lost.
    Their DB rows remain in PENDING/SCANNING/PROCESSING indefinitely.  This
    function cleans them up immediately so the admin UI reflects reality and
    new ingestion triggers are not blocked.
    """
    from datetime import datetime, timezone

    from sqlalchemy import update as sa_update

    from app.domain.ingestion.models import IngestionJob, IngestionStatus
    from app.infra.database import _session_factory

    if _session_factory is None:
        return

    active_statuses = [
        IngestionStatus.PENDING,
        IngestionStatus.SCANNING,
        IngestionStatus.PROCESSING,
    ]

    async with _session_factory() as db:
        stmt = (
            sa_update(IngestionJob)
            .where(IngestionJob.status.in_(active_statuses))
            .values(
                status=IngestionStatus.FAILED,
                error_message="Auto-failed: worker restarted while job was in-flight",
                completed_at=datetime.now(timezone.utc),
            )
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(stmt)
        if result.rowcount:
            await db.commit()
            logger.warning(
                "Auto-failed %d zombie ingestion job(s) on worker startup",
                result.rowcount,
            )
        else:
            logger.info("No zombie ingestion jobs found on startup")
