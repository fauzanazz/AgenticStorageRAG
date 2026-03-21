"""Celery tasks for document processing.

These tasks are discovered automatically by the Celery worker via
the `imports` list in `app/celery_app.py`.

Each task wraps the async domain service call using asyncio.run().
Celery workers run tasks in a thread pool (-P threads), so asyncio.run()
is safe — each task invocation gets its own fresh event loop.
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
    retry_backoff=True,  # 2s, 4s, 8s
    retry_backoff_max=60,
    acks_late=True,
)
def process_document_task(self, *, document_id: str) -> None:  # type: ignore[misc]
    """Process a document: extract text, chunk, embed, build KG.

    Args:
        document_id: UUID string of the document to process.
    """
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
def cleanup_expired_task(self) -> None:  # type: ignore[misc]
    """Remove expired documents from storage, DB, Neo4j, and pgvector."""
    from app.domain.documents.service import DocumentService

    async def _run() -> None:
        async for db in get_db_session():
            service = DocumentService(db=db, storage=storage_client)
            await service.cleanup_expired()

    asyncio.run(_run())
    logger.info("Expired documents cleaned up")
