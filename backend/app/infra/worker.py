"""Background worker — compatibility shim.

The custom Redis poll-loop worker has been replaced by Celery.

New worker entrypoint:
    celery -A app.celery_app worker \\
        --loglevel=info \\
        --concurrency=4 \\
        -P threads \\
        -Q documents,ingestion,knowledge

See app/celery_app.py for the Celery application and
app/domain/*/tasks.py for the task definitions.

This shim keeps the following names importable so that existing code
(documents/router.py imports QUEUE_DOCUMENTS, domain jobs.py files
import register_handler) does not break before those files are cleaned up.
"""

from __future__ import annotations

from typing import Any, Callable

# Queue name constants — kept for backward compatibility
QUEUE_DOCUMENTS = "jobs:documents"
QUEUE_KNOWLEDGE = "jobs:knowledge"
QUEUE_INGESTION = "jobs:ingestion"
ALL_QUEUES = [QUEUE_DOCUMENTS, QUEUE_KNOWLEDGE, QUEUE_INGESTION]


def register_handler(job_type: str, handler: Callable[..., Any]) -> None:
    """No-op shim. Handlers are now registered as Celery tasks in tasks.py."""
    pass
