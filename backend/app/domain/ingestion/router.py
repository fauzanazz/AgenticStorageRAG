"""Ingestion domain router.

Admin-only endpoints for managing base KG ingestion from Google Drive.
Not exposed to end users -- only accessible by admin (is_admin=True on User).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_storage
from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.schemas import (
    IngestionJobListResponse,
    IngestionJobResponse,
    TriggerIngestionRequest,
)
from app.domain.ingestion.service import IngestionService
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])


async def _require_admin(user: "User" = Depends(get_current_user)) -> "User":
    """Dependency that ensures the current user is an admin.

    Raises:
        HTTPException 403 if user is not admin
    """
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def _get_service(
    db: AsyncSession = Depends(get_db),
    storage: StorageClient = Depends(get_storage),
) -> IngestionService:
    """Provide IngestionService as a dependency."""
    return IngestionService(db=db, storage=storage)


@router.post(
    "/trigger",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a new ingestion job",
    description="Starts ingesting files from Google Drive into the base Knowledge Graph. Admin only.",
)
async def trigger_ingestion(
    request: TriggerIngestionRequest = TriggerIngestionRequest(),
    user: "User" = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionJobResponse:
    """Trigger a new ingestion job from Google Drive."""
    try:
        return await service.trigger_ingestion(
            request=request,
            admin_user_id=user.id,
        )
    except IngestionAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        ) from e
    except IngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
        ) from e


@router.get(
    "/jobs",
    response_model=IngestionJobListResponse,
    summary="List ingestion jobs",
)
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    _user: "User" = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionJobListResponse:
    """List all ingestion jobs (newest first)."""
    return await service.list_jobs(page=page, page_size=page_size)


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get ingestion job details",
)
async def get_job(
    job_id: uuid.UUID,
    _user: "User" = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionJobResponse:
    """Get details for a specific ingestion job."""
    try:
        return await service.get_job(job_id)
    except IngestionJobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        ) from e


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=IngestionJobResponse,
    summary="Cancel a running ingestion job",
)
async def cancel_job(
    job_id: uuid.UUID,
    _user: "User" = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionJobResponse:
    """Cancel a running ingestion job."""
    try:
        return await service.cancel_job(job_id)
    except IngestionJobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        ) from e
