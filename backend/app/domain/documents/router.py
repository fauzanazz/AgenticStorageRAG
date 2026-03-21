"""Documents domain router.

REST endpoints for document upload, listing, retrieval, and deletion.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user_id, get_db, get_storage
from app.domain.documents.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.documents.schemas import (
    DashboardStatsResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DriveTreeResponse,
)
from app.domain.documents.service import DocumentService
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


def _get_document_service(
    db: AsyncSession = Depends(get_db),
    storage: StorageClient = Depends(get_storage),
) -> DocumentService:
    return DocumentService(db=db, storage=storage)


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    file: UploadFile,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DocumentService = Depends(_get_document_service),
) -> DocumentUploadResponse:
    """Upload a PDF or DOCX file for processing.

    The file is stored and queued for background processing.
    Processing extracts text, creates chunks, and prepares for RAG queries.
    Uploaded files expire after 7 days.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    content = await file.read()

    try:
        result = await service.upload(
            user_id=user_id,
            filename=file.filename,
            file_content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except UnsupportedFileTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(e),
        ) from e
    except FileTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        ) from e

    # Queue background processing job via Celery -- fail gracefully
    try:
        from app.domain.documents.tasks import process_document_task

        process_document_task.delay(document_id=str(result.id))
    except Exception:
        logger.exception("Failed to dispatch document processing task: %s", result.id)
        # Document is uploaded but not queued -- admin can retry manually

    return result


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    source: str | None = Query(None, description="Filter by source: 'upload' or 'google_drive'"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DocumentService = Depends(_get_document_service),
) -> DocumentListResponse:
    """List all documents for the authenticated user."""
    return await service.list_documents(
        user_id=user_id,
        page=page,
        page_size=page_size,
        source=source,
    )


@router.get(
    "/drive-tree",
    response_model=DriveTreeResponse,
    summary="Get Drive documents as a folder tree",
)
async def get_drive_tree(
    service: DocumentService = Depends(_get_document_service),
) -> DriveTreeResponse:
    """Return all indexed Drive files organised into a folder tree."""
    return await service.get_drive_tree()


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(
    document_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DocumentService = Depends(_get_document_service),
) -> DocumentResponse:
    """Get details of a specific document."""
    try:
        return await service.get_document(document_id=document_id, user_id=user_id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DocumentService = Depends(_get_document_service),
) -> None:
    """Delete a document and all its chunks."""
    try:
        await service.delete_document(document_id=document_id, user_id=user_id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get(
    "/stats/dashboard",
    response_model=DashboardStatsResponse,
    summary="Get dashboard stats",
)
async def get_dashboard_stats(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: DocumentService = Depends(_get_document_service),
) -> DashboardStatsResponse:
    """Get aggregated stats for the user dashboard."""
    return await service.get_dashboard_stats(user_id=user_id)
