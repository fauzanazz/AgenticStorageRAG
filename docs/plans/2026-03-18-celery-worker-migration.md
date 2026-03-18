# Celery Worker Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the custom Redis + poll-loop worker with Celery, fix sequential queue starvation, and wrap all synchronous Google Drive `.execute()` calls in `asyncio.to_thread()`.

**Architecture:** Celery uses Redis as the broker (same Redis instance, different key namespace so no data migration). Each job type becomes a Celery task in its domain's `tasks.py` file. The API enqueues by calling `task.delay()` instead of `redis_client.enqueue()`. The worker process becomes `celery -A app.celery_app worker`. Concurrency within the worker uses Celery's built-in `--concurrency` flag (gevent or threads), eliminating the sequential poll loop starvation.

**Tech Stack:** `celery>=5.4`, `redis>=5.2` (already present), Python 3.12, asyncio, `asyncio.to_thread()` for Drive I/O.

---

## What changes and what doesn't

| | Before | After |
|---|---|---|
| Queue broker | Redis lists via custom `RedisClient.enqueue()` | Celery broker on same Redis (`redis://redis:6379/1` — DB 1 to separate from cache DB 0) |
| Worker entrypoint | `python -m app.infra.worker` | `celery -A app.celery_app worker` |
| Concurrency | Sequential per-queue poll (starves) | Celery `--concurrency=4 -P threads` (all queues simultaneously) |
| Job dispatch | `redis_client.enqueue("jobs:documents", {...})` | `process_document_task.delay(document_id=str(id))` |
| Retry policy | Hand-rolled in `worker.py` (3 retries, exp backoff) | `autoretry_for`, `max_retries=3`, `default_retry_delay=2` in task decorator |
| Dead-letter | `dlq:<queue>` Redis list (manual inspection) | Celery's built-in dead-letter via `acks_late=True` + DLQ route |
| Drive blocking I/O | Blocks asyncio event loop | Wrapped in `asyncio.to_thread()` |
| `infra/worker.py` | ~230 lines of custom polling logic | Replaced by `app/celery_app.py` (~60 lines) |
| `infra/redis_client.py` | Queue ops + cache ops | Cache ops only (enqueue/dequeue/move_to_dlq removed) |
| Docker Compose | `command: python -m app.infra.worker` | `command: celery -A app.celery_app worker --loglevel=info --concurrency=4 -P threads -Q documents,ingestion,knowledge` |

**`infra/redis_client.py` is NOT deleted** — the API server still uses it for `get`/`set`/`delete` cache operations. Only the 4 queue methods are removed.

---

## Task 1: Add Celery dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock` (auto-updated by uv)

**Step 1: Add celery to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list after `redis>=5.2.0`:

```toml
"celery[redis]>=5.4.0",
```

**Step 2: Install**

```bash
cd backend && uv pip install --system -e ".[dev]"
```

Expected: `Installed celery-5.x.x` in output.

**Step 3: Verify import**

```bash
cd backend && uv run python -c "import celery; print(celery.__version__)"
```

Expected: prints a version like `5.4.x`.

**Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): add celery[redis]>=5.4.0"
```

---

## Task 2: Create `app/celery_app.py` — the Celery application singleton

**Files:**
- Create: `backend/app/celery_app.py`

This file replaces `app/infra/worker.py` as the worker entrypoint.

**Step 1: Create the file**

```python
"""Celery application factory.

This module creates the Celery app singleton used by:
  - The worker process: celery -A app.celery_app worker
  - The API server: importing task functions to call .delay()

Queue layout (all on Redis DB 1 to separate from cache on DB 0):
  documents  — document processing jobs
  ingestion  — Google Drive ingestion jobs
  knowledge  — KG extraction jobs (reserved for future use)

Retry policy is defined per-task via autoretry_for / max_retries /
default_retry_delay in the task decorator — not in a central handler.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init

from app.config import get_settings

logger = logging.getLogger(__name__)


def _broker_url() -> str:
    """Build the Celery broker URL from settings.

    Uses Redis DB 1 to keep Celery keys separate from the app cache
    (DB 0). The REDIS_URL in settings is for DB 0 (e.g.
    redis://redis:6379/0); we replace the trailing /0 with /1.
    """
    settings = get_settings()
    url = str(settings.redis_url)
    # Replace the database index: .../0 → .../1
    if url.endswith("/0"):
        return url[:-1] + "1"
    return url + "/celery"


def create_celery_app() -> Celery:
    app = Celery("dingdong_rag")

    app.conf.update(
        broker_url=_broker_url(),
        result_backend=_broker_url(),

        # Route each task to a dedicated queue
        task_routes={
            "app.domain.documents.tasks.*": {"queue": "documents"},
            "app.domain.ingestion.tasks.*": {"queue": "ingestion"},
            "app.domain.knowledge.tasks.*": {"queue": "knowledge"},
        },

        # Acknowledge task only after it completes (enables at-least-once delivery)
        task_acks_late=True,
        # Reject and requeue on worker crash (SIGKILL / OOM)
        task_reject_on_worker_lost=True,

        # Serialisation
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,

        # Autodiscover tasks in domain packages
        # Each domain exposes its tasks in a `tasks.py` module.
        imports=[
            "app.domain.documents.tasks",
            "app.domain.ingestion.tasks",
        ],
    )

    return app


celery_app = create_celery_app()


@worker_process_init.connect
def _init_worker_resources(**kwargs: object) -> None:
    """Initialise shared resources once per worker process.

    Celery forks worker processes; each fork must re-initialise
    connections (DB, Redis cache, storage, LLM) because file descriptors
    are not safely shared across fork boundaries.
    """
    import asyncio

    from app.infra.database import init_db
    from app.infra.llm import llm_provider
    from app.infra.storage import storage_client

    init_db()
    storage_client.connect()
    llm_provider.initialize()

    logger.info("Worker process resources initialised")
```

**Step 2: Verify it imports**

```bash
cd backend && uv run python -c "from app.celery_app import celery_app; print('Celery app OK:', celery_app)"
```

Expected: `Celery app OK: <Celery dingdong_rag ...>` — no errors.

**Step 3: Commit**

```bash
git add backend/app/celery_app.py
git commit -m "feat(worker): add Celery app singleton with Redis broker and task routing"
```

---

## Task 3: Wrap all Google Drive `.execute()` calls in `asyncio.to_thread()`

**Files:**
- Modify: `backend/app/domain/ingestion/drive_connector.py`

There are 5 synchronous `.execute()` call sites to wrap. All live inside methods that are already declared `async`, so the fix is mechanical: replace `thing.execute()` with `await asyncio.run_coroutine_threadsafe(asyncio.to_thread(thing.execute), asyncio.get_event_loop())` — but simpler: just `await asyncio.to_thread(thing.execute)`.

**Step 1: Add `asyncio` import at the top of `drive_connector.py`**

The file already has `import asyncio`? Check:

```bash
cd backend && head -20 app/domain/ingestion/drive_connector.py | grep asyncio
```

If not present, add `import asyncio` after the existing stdlib imports.

**Step 2: Wrap site 1 — `authenticate()` connectivity test**

Find (around line 138–140):
```python
            result = self._service.files().list(
                pageSize=1, fields="files(id)"
            ).execute()
```

Replace with:
```python
            request = self._service.files().list(pageSize=1, fields="files(id)")
            result = await asyncio.to_thread(request.execute)
```

**Step 3: Wrap site 2 — `list_files()` paginated listing**

Find (around line 183–189):
```python
            response = self._service.files().list(
                ...
            ).execute()
```

Replace with:
```python
            request = self._service.files().list(...)
            response = await asyncio.to_thread(request.execute)
```

**Step 4: Wrap site 3 — `download_file()` metadata fetch**

Find (around line 234–236):
```python
            file_metadata = self._service.files().get(
                fileId=file_id, fields=FILE_FIELDS
            ).execute()
```

Replace with:
```python
            meta_request = self._service.files().get(fileId=file_id, fields=FILE_FIELDS)
            file_metadata = await asyncio.to_thread(meta_request.execute)
```

**Step 5: Wrap site 4 — `download_file()` MediaIoBaseDownload loop**

The `MediaIoBaseDownload` downloader calls `.next_chunk()` synchronously in a while loop. Find the download loop (around line 240–260) and wrap each `.next_chunk()`:

Before:
```python
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
```

After:
```python
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = await asyncio.to_thread(downloader.next_chunk)
```

**Step 6: Wrap site 5 — `get_file_metadata()`**

Find (around line 275–279):
```python
            return self._service.files().get(
                fileId=file_id, fields=...
            ).execute()
```

Replace with:
```python
            request = self._service.files().get(fileId=file_id, fields=...)
            return await asyncio.to_thread(request.execute)
```

**Step 7: Wrap site 6 — `list_folder_children()` paginated listing**

Find (around line 308–315) — this is the production hot path:
```python
            response = self._service.files().list(
                ...
            ).execute()
```

Replace with:
```python
            request = self._service.files().list(...)
            response = await asyncio.to_thread(request.execute)
```

**Step 8: Verify no `.execute()` calls remain un-wrapped**

```bash
cd backend && grep -n "\.execute()" app/domain/ingestion/drive_connector.py
```

Expected output: empty (zero results).

**Step 9: Run import check**

```bash
cd backend && uv run python -c "from app.domain.ingestion.drive_connector import GoogleDriveConnector; print('OK')"
```

**Step 10: Commit**

```bash
git add backend/app/domain/ingestion/drive_connector.py
git commit -m "fix(ingestion): wrap all Google Drive .execute() calls in asyncio.to_thread() to unblock event loop"
```

---

## Task 4: Create `app/domain/documents/tasks.py` — Celery document tasks

**Files:**
- Create: `backend/app/domain/documents/tasks.py`
- Reference: `backend/app/domain/documents/jobs.py` (old handler logic to port)

**Step 1: Write the failing test first**

Create `backend/app/domain/documents/tests/test_tasks.py`:

```python
"""Tests for Celery document tasks."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProcessDocumentTask:
    def test_task_is_registered(self):
        """Task must be importable and registered with Celery."""
        from app.domain.documents.tasks import process_document_task
        assert process_document_task is not None
        assert process_document_task.name == "app.domain.documents.tasks.process_document_task"

    def test_task_queue(self):
        """Task must target the documents queue."""
        from app.domain.documents.tasks import process_document_task
        # Celery routes are defined in celery_app.py; verify task name prefix matches route
        assert process_document_task.name.startswith("app.domain.documents.tasks.")

    @patch("app.domain.documents.tasks.get_db_session")
    @patch("app.domain.documents.tasks.storage_client")
    @patch("app.domain.documents.tasks.DocumentService")
    def test_process_document_calls_service(
        self, mock_service_cls, mock_storage, mock_get_db
    ):
        """process_document_task must call DocumentService.process_document."""
        from app.domain.documents.tasks import process_document_task

        document_id = str(uuid.uuid4())

        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_service = AsyncMock()
        mock_service_cls.return_value = mock_service

        # Run the underlying coroutine directly (bypasses Celery machinery)
        import asyncio
        asyncio.run(process_document_task.run(document_id=document_id))

        mock_service.process_document.assert_awaited_once()
```

Run: `cd backend && uv run pytest app/domain/documents/tests/test_tasks.py -v`

Expected: **FAIL** — `ImportError: cannot import name 'process_document_task'`.

**Step 2: Implement `documents/tasks.py`**

```python
"""Celery tasks for document processing.

These tasks are discovered automatically by the Celery worker via
the `imports` list in `app/celery_app.py`.

Each task wraps the async domain service call using asyncio.run().
Celery workers run tasks in a thread pool (-P threads), so asyncio.run()
is safe here — each task gets its own event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.celery_app import celery_app
from app.infra.database import get_db_session
from app.infra.storage import storage_client

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.domain.documents.tasks.process_document_task",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    autoretry_for=(Exception,),
    retry_backoff=True,         # 2s, 4s, 8s
    retry_backoff_max=60,
    acks_late=True,
)
def process_document_task(self, *, document_id: str) -> None:
    """Process a document: extract text, chunk, embed, build KG."""
    from app.domain.documents.service import DocumentService

    doc_uuid = uuid.UUID(document_id)

    async def _run() -> None:
        async for db in get_db_session():
            service = DocumentService(db=db, storage=storage_client)
            await service.process_document(doc_uuid)

    asyncio.run(_run())
    logger.info("Document processed: %s", document_id)


@celery_app.task(
    name="app.domain.documents.tasks.cleanup_expired_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    acks_late=True,
)
def cleanup_expired_task(self) -> None:
    """Remove expired documents from storage, DB, Neo4j, and pgvector."""
    from app.domain.documents.service import DocumentService

    async def _run() -> None:
        async for db in get_db_session():
            service = DocumentService(db=db, storage=storage_client)
            await service.cleanup_expired()

    asyncio.run(_run())
    logger.info("Expired documents cleaned up")
```

**Step 3: Run the tests**

```bash
cd backend && uv run pytest app/domain/documents/tests/test_tasks.py -v
```

Expected: **PASS** (3/3).

**Step 4: Commit**

```bash
git add backend/app/domain/documents/tasks.py backend/app/domain/documents/tests/test_tasks.py
git commit -m "feat(documents): add Celery tasks for document processing"
```

---

## Task 5: Create `app/domain/ingestion/tasks.py` — Celery ingestion task

**Files:**
- Create: `backend/app/domain/ingestion/tasks.py`
- Reference: `backend/app/domain/ingestion/jobs.py` (old handler logic to port)

**Step 1: Write the failing test**

Create `backend/app/domain/ingestion/tests/test_tasks.py`:

```python
"""Tests for Celery ingestion tasks."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunIngestionTask:
    def test_task_is_registered(self):
        from app.domain.ingestion.tasks import run_ingestion_task
        assert run_ingestion_task is not None
        assert run_ingestion_task.name == "app.domain.ingestion.tasks.run_ingestion_task"

    def test_task_queue_prefix(self):
        from app.domain.ingestion.tasks import run_ingestion_task
        assert run_ingestion_task.name.startswith("app.domain.ingestion.tasks.")

    @patch("app.domain.ingestion.tasks._session_factory")
    @patch("app.domain.ingestion.tasks.llm_provider")
    @patch("app.domain.ingestion.tasks.storage_client")
    @patch("app.domain.ingestion.tasks.GoogleDriveConnector")
    @patch("app.domain.ingestion.tasks.IngestionOrchestrator")
    def test_run_ingestion_calls_orchestrator(
        self,
        mock_orchestrator_cls,
        mock_connector_cls,
        mock_storage,
        mock_llm,
        mock_session_factory,
    ):
        from app.domain.ingestion.tasks import run_ingestion_task

        job_id = str(uuid.uuid4())
        admin_user_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        mock_job = MagicMock()
        mock_session.get = AsyncMock(return_value=mock_job)

        mock_orchestrator = AsyncMock()
        mock_orchestrator_cls.return_value = mock_orchestrator

        import asyncio
        asyncio.run(run_ingestion_task.run(job_id=job_id, admin_user_id=admin_user_id, force=False))

        mock_orchestrator.run.assert_awaited_once()
```

Run: `cd backend && uv run pytest app/domain/ingestion/tests/test_tasks.py::TestRunIngestionTask::test_task_is_registered -v`

Expected: **FAIL** — `ImportError`.

**Step 2: Implement `ingestion/tasks.py`**

```python
"""Celery tasks for Google Drive ingestion.

The IngestionOrchestrator is a long-running ReAct agent (up to 500
iterations). It runs inside the Celery task, which executes in a thread
(-P threads). Each iteration involves: LLM call → Drive I/O (now
non-blocking via asyncio.to_thread) → DB write.

Note on retries: ingestion tasks are NOT auto-retried on failure because
the orchestrator manages its own internal error handling and progress
tracking. A failed ingestion job is recorded in the DB with status
FAILED; the admin can re-trigger manually.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.celery_app import celery_app
from app.domain.ingestion.models import IngestionJob
from app.infra.database import _session_factory
from app.infra.llm import llm_provider
from app.infra.storage import storage_client

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.domain.ingestion.tasks.run_ingestion_task",
    bind=True,
    # No autoretry: the orchestrator handles its own failure state.
    # A crashed task (SIGKILL) will be redelivered once by Celery
    # (acks_late=True in celery_app.py).
    max_retries=0,
    acks_late=True,
    time_limit=7200,    # 2-hour hard kill for runaway jobs
    soft_time_limit=6900,  # 115-min soft limit (raises SoftTimeLimitExceeded)
)
def run_ingestion_task(self, *, job_id: str, admin_user_id: str, force: bool = False) -> None:
    """Run the IngestionOrchestrator for a triggered Google Drive ingestion job."""
    from app.domain.ingestion.drive_connector import GoogleDriveConnector
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
                raise  # Let Celery record the failure

    asyncio.run(_run())
```

**Step 3: Run the tests**

```bash
cd backend && uv run pytest app/domain/ingestion/tests/test_tasks.py -v
```

Expected: **PASS** (3/3).

**Step 4: Commit**

```bash
git add backend/app/domain/ingestion/tasks.py backend/app/domain/ingestion/tests/test_tasks.py
git commit -m "feat(ingestion): add Celery task for Google Drive ingestion orchestrator"
```

---

## Task 6: Update dispatch sites — replace `redis_client.enqueue()` with `.delay()`

**Files:**
- Modify: `backend/app/domain/documents/service.py` (find `redis_client.enqueue`)
- Modify: `backend/app/domain/ingestion/service.py` (find `redis_client.enqueue`)

**Step 1: Find all enqueue call sites**

```bash
cd backend && grep -rn "redis_client.enqueue" app/
```

Note each file and line number. Expected: `documents/service.py` and `ingestion/service.py`.

**Step 2: Update `documents/service.py`**

Find the call that looks like:
```python
await redis_client.enqueue("jobs:documents", {"type": "process_document", "document_id": str(document.id)})
```

Replace with:
```python
from app.domain.documents.tasks import process_document_task
process_document_task.delay(document_id=str(document.id))
```

Remove the `from app.infra.redis_client import redis_client` import from this file **only if** `redis_client` is no longer used for anything else in `documents/service.py`. If it is used for caching elsewhere, keep the import.

**Step 3: Update `ingestion/service.py`**

Find the call that looks like:
```python
await redis_client.enqueue("jobs:ingestion", {"type": "run_ingestion", "job_id": str(job.id), ...})
```

Replace with:
```python
from app.domain.ingestion.tasks import run_ingestion_task
run_ingestion_task.delay(job_id=str(job.id), admin_user_id=str(admin_user_id), force=force)
```

**Step 4: Verify no `jobs:documents` or `jobs:ingestion` strings remain as producers**

```bash
cd backend && grep -rn "jobs:documents\|jobs:ingestion" app/ | grep -v "worker.py\|test_"
```

Expected: zero results (only `worker.py` and old tests might mention them, and those are being replaced).

**Step 5: Run existing service tests to confirm nothing broke**

```bash
cd backend && uv run pytest app/domain/documents/tests/ app/domain/ingestion/tests/ -v --no-cov -q
```

Expected: all pass (service tests mock `redis_client` or don't test dispatch directly).

**Step 6: Commit**

```bash
git add backend/app/domain/documents/service.py backend/app/domain/ingestion/service.py
git commit -m "feat(worker): switch job dispatch from redis_client.enqueue() to Celery .delay()"
```

---

## Task 7: Strip queue methods from `infra/redis_client.py`

**Files:**
- Modify: `backend/app/infra/redis_client.py`
- Modify: `backend/app/infra/tests/test_redis.py` (if it tests queue methods)

The four queue methods (`enqueue`, `dequeue`, `move_to_dlq`, `queue_length`, `dlq_length`) are now owned by Celery. Remove them from `RedisClient` to avoid confusion. The cache methods (`get`, `set`, `delete`, `get_json`, `set_json`, `connect`, `close`) stay.

**Step 1: Check if tests exist for queue methods**

```bash
cd backend && grep -n "enqueue\|dequeue\|move_to_dlq\|queue_length\|dlq_length" app/infra/tests/test_redis.py 2>/dev/null || echo "no queue tests"
```

If tests exist for those methods, delete only those test cases.

**Step 2: Remove the 5 queue methods from `RedisClient`**

Methods to remove from `redis_client.py`:
- `enqueue()`
- `dequeue()`
- `move_to_dlq()`
- `queue_length()`
- `dlq_length()`

Keep: `connect()`, `close()`, `get()`, `set()`, `delete()`, `get_json()`, `set_json()`, and all other non-queue methods.

**Step 3: Verify no remaining callers of removed methods**

```bash
cd backend && grep -rn "redis_client\.enqueue\|redis_client\.dequeue\|redis_client\.move_to_dlq\|redis_client\.queue_length\|redis_client\.dlq_length" app/
```

Expected: zero results.

**Step 4: Run redis tests**

```bash
cd backend && uv run pytest app/infra/tests/test_redis.py -v --no-cov
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/infra/redis_client.py backend/app/infra/tests/
git commit -m "refactor(redis): remove queue methods — now handled by Celery"
```

---

## Task 8: Replace `infra/worker.py` with a thin compatibility shim

**Files:**
- Modify: `backend/app/infra/worker.py`

`worker.py` cannot simply be deleted because `documents/jobs.py` and `ingestion/jobs.py` still `import register_handler` from it (for now). Instead of deleting it immediately, replace it with a tiny shim that keeps the module importable but makes clear it is deprecated.

Also `QUEUE_DOCUMENTS`, `QUEUE_KNOWLEDGE`, `QUEUE_INGESTION` constants may still be referenced in tests — keep the constants, remove the loop logic.

**Step 1: Replace `worker.py` contents**

```python
"""Background worker — DEPRECATED.

The custom poll-loop worker has been replaced by Celery.
This module is kept as a compatibility shim so that any code still
importing QUEUE_* constants or register_handler() does not break
immediately. These symbols will be removed in a follow-up cleanup.

New worker entrypoint:
    celery -A app.celery_app worker --loglevel=info \\
           --concurrency=4 -P threads \\
           -Q documents,ingestion,knowledge

See app/celery_app.py and app/domain/*/tasks.py.
"""

# Queue name constants — kept for backward compatibility with tests
QUEUE_DOCUMENTS = "jobs:documents"
QUEUE_KNOWLEDGE = "jobs:knowledge"
QUEUE_INGESTION = "jobs:ingestion"
ALL_QUEUES = [QUEUE_DOCUMENTS, QUEUE_KNOWLEDGE, QUEUE_INGESTION]


def register_handler(*args: object, **kwargs: object) -> None:
    """No-op shim. Handlers are now registered as Celery tasks in tasks.py."""
    pass
```

**Step 2: Verify app still imports**

```bash
cd backend && uv run python -c "from app.main import app; print('App OK')"
```

**Step 3: Run full test suite**

```bash
cd backend && uv run pytest app/ -q --no-cov 2>&1 | tail -10
```

Expected: same pass count as before (no new failures).

**Step 4: Commit**

```bash
git add backend/app/infra/worker.py
git commit -m "refactor(worker): replace custom poll-loop worker with Celery compatibility shim"
```

---

## Task 9: Update Docker Compose — swap worker command to Celery

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Update both worker services**

For `worker-local` (line ~110) and `worker-supabase` (line ~189), change:

```yaml
command: python -m app.infra.worker
```

to:

```yaml
command: >
  celery -A app.celery_app worker
  --loglevel=info
  --concurrency=4
  -P threads
  -Q documents,ingestion,knowledge
```

Also update the `deploy.replicas` comment since we no longer need multiple replicas for concurrency (Celery handles it internally with `--concurrency=4`). Change replicas from `2` to `1`:

```yaml
deploy:
  replicas: 1  # Celery --concurrency=4 handles parallelism internally; scale replicas for job throughput
```

**Step 2: Change Redis DB from 0 to keep cache on 0 and Celery on 1**

The `REDIS_URL` env var in both worker services uses DB 0, and `celery_app.py` already switches to DB 1 in `_broker_url()`. No change needed to the compose file for this — it is handled in code.

**Step 3: Verify docker-compose is valid**

```bash
docker compose --profile supabase config --quiet
```

Expected: no output (valid YAML, no errors).

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(docker): switch worker containers to Celery with --concurrency=4 -P threads"
```

---

## Task 10: Update Makefile — add Celery dev command

**Files:**
- Modify: `Makefile`

**Step 1: Add a `dev-worker` target**

Find the existing `dev-backend` target (or similar) in the Makefile and add alongside it:

```makefile
dev-worker: ## Run Celery worker locally (outside Docker)
	cd backend && uv run celery -A app.celery_app worker \
		--loglevel=info \
		--concurrency=4 \
		-P threads \
		-Q documents,ingestion,knowledge
```

Also update the `help` comments on any existing worker-related targets if they reference the old `python -m app.infra.worker` command.

**Step 2: Verify make help works**

```bash
make help 2>&1 | grep -i worker
```

Expected: shows the new `dev-worker` target.

**Step 3: Commit**

```bash
git add Makefile
git commit -m "chore(makefile): add dev-worker target for Celery worker"
```

---

## Task 11: Update `AGENTS.md` and `backend/app/infra/worker.py` docstring

**Files:**
- Modify: `AGENTS.md` — update the worker process model table and the "Backend process model" section
- Modify: `backend/app/infra/worker.py` shim (already done in Task 8)

**Step 1: Update AGENTS.md**

Find the "Backend process model" table in `AGENTS.md` (near the top of the architecture section):

Old:
```markdown
| Worker | `python -m app.infra.worker` | Processes Redis queue jobs |
```

New:
```markdown
| Worker | `celery -A app.celery_app worker --concurrency=4 -P threads -Q documents,ingestion,knowledge` | Processes Celery tasks (documents, ingestion) |
```

Also update gotcha #3 ("Worker `__main__` / `app.infra.worker` dual-module problem") — this problem no longer exists with Celery. Replace the gotcha body with a note that it was resolved by the Celery migration.

Also update gotcha #18 ("Worker poll loop is sequential across queues within one iteration") — this is also resolved. Update it accordingly.

**Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): update worker process model and resolved gotchas for Celery migration"
```

---

## Task 12: Final verification

**Step 1: Run full backend test suite**

```bash
cd backend && uv run pytest app/ -q --no-cov 2>&1 | tail -5
```

Expected: all tests pass (same count as before).

**Step 2: Rebuild and start the worker container**

```bash
docker compose --profile supabase up -d --build worker-supabase
```

**Step 3: Check worker logs for successful startup**

```bash
sleep 10 && docker logs $(docker ps -q --filter name=worker-supabase) 2>&1 | tail -30
```

Expected log lines:
```
[config]
.> app:         dingdong_rag
.> transport:   redis://redis:6379/1
.> results:     redis://redis:6379/1
.> concurrency: 4 (threads)
.> task events: OFF (enable -E to monitor tasks)

[queues]
.> documents         exchange=documents(direct) key=documents
.> ingestion         exchange=ingestion(direct) key=ingestion
.> knowledge         exchange=knowledge(direct) key=knowledge

[tasks]
  . app.domain.documents.tasks.process_document_task
  . app.domain.documents.tasks.cleanup_expired_task
  . app.domain.ingestion.tasks.run_ingestion_task

[2026-...] celery@... ready.
```

**Step 4: Smoke test — dispatch a document task manually**

```bash
docker exec $(docker ps -q --filter name=backend-supabase) \
  uv run python -c "
from app.domain.documents.tasks import process_document_task
import uuid
# Dispatch a fake UUID — will fail in the handler (doc not found) but proves routing works
result = process_document_task.delay(document_id=str(uuid.uuid4()))
print('Task ID:', result.id)
print('Task dispatched OK')
"
```

Expected: prints a Celery task ID. The worker log will show the task received and fail with "Document not found" — this is expected for a fake UUID.

**Step 5: Commit final**

```bash
git add .
git commit -m "chore: final verification — Celery worker migration complete"
```

---

## What is NOT changing

| Item | Reason |
|---|---|
| `infra/redis_client.py` (cache ops) | Still used by the API server for caching; only queue ops removed |
| `infra/database.py` | No change |
| `infra/llm.py` | No change |
| `infra/neo4j_client.py` | No change |
| `infra/storage.py` | No change |
| `domain/documents/jobs.py` | Kept as-is (shim `register_handler` makes it a no-op); can be deleted in follow-up |
| `domain/ingestion/jobs.py` | Same as above |
| `domain/ingestion/orchestrator.py` | No change — runs inside the Celery task |
| `domain/ingestion/orchestrator_tools.py` | No change — Drive I/O fixed in `drive_connector.py` |
| Frontend | No change |
| OpenAPI contract | No change (job dispatch is an implementation detail) |
| Neo4j | No change |
| Alembic migrations | No change |

---

## Dependency map (wave ordering for parallel execution)

```
Task 1  (add celery dep)
  └── Task 2  (celery_app.py)
        ├── Task 4  (documents/tasks.py)
        │     └── Task 6  (update dispatch sites)
        │           └── Task 7  (strip redis queue methods)
        │                 └── Task 8  (worker.py shim)
        │                       └── Task 9  (docker-compose)
        │                             └── Task 10  (Makefile)
        │                                   └── Task 12  (final verify)
        └── Task 5  (ingestion/tasks.py)       ↗
Task 3  (asyncio.to_thread Drive wrapping) ────┘  (independent, can run in parallel with Task 2+)
Task 11 (AGENTS.md docs) — independent, anytime after Task 8
```

Wave 1 (parallel): Task 1, Task 3
Wave 2 (parallel): Task 2, (Task 3 continues if not done)
Wave 3 (parallel): Task 4, Task 5
Wave 4 (sequential): Task 6 → Task 7 → Task 8
Wave 5 (parallel): Task 9, Task 10, Task 11
Wave 6 (sequential): Task 12
