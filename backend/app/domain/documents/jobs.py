"""Background job handler for document processing.

Registered with the worker to handle 'process_document' jobs.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.domain.documents.service import DocumentService
from app.infra.database import get_db_session
from app.infra.storage import storage_client
from app.infra.worker import register_handler

logger = logging.getLogger(__name__)


async def handle_process_document(job_data: dict[str, Any]) -> None:
    """Handle a document processing job.

    Called by the worker process when a 'process_document' job is dequeued.

    Args:
        job_data: Must contain 'document_id' key with UUID string
    """
    document_id_str = job_data.get("document_id")
    if not document_id_str:
        logger.error("process_document job missing 'document_id': %s", job_data)
        return

    document_id = uuid.UUID(document_id_str)

    # Create a fresh DB session for this job
    async for db in get_db_session():
        service = DocumentService(db=db, storage=storage_client)
        try:
            await service.process_document(document_id)
            logger.info("Document processing completed: %s", document_id)
        except Exception:
            logger.exception("Document processing failed: %s", document_id)


async def handle_cleanup_expired(job_data: dict[str, Any]) -> None:
    """Handle an expired documents cleanup job.

    Called periodically (e.g., via cron or scheduled task) to clean up
    documents past their 7-day TTL.
    """
    async for db in get_db_session():
        service = DocumentService(db=db, storage=storage_client)
        try:
            count = await service.cleanup_expired()
            logger.info("Expired documents cleanup completed: %d removed", count)
        except Exception:
            logger.exception("Expired documents cleanup failed")


def register_document_handlers() -> None:
    """Register all document-related job handlers with the worker."""
    register_handler("process_document", handle_process_document)
    register_handler("cleanup_expired", handle_cleanup_expired)
    logger.info("Document job handlers registered")
