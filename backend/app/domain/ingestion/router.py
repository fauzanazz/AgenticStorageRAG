"""Ingestion domain router.

Admin-only endpoints for managing base KG ingestion from Google Drive.
Not exposed to end users -- only accessible by admin (is_admin=True on User).
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.domain.auth.models import User

from app.dependencies import get_current_user, get_db, get_storage
from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.schemas import (
    DefaultFolderResponse,
    DriveBrowseEntry,
    DriveFolderEntry,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionStatsResponse,
    ProviderInfo,
    SaveDefaultFolderRequest,
    TriggerIngestionRequest,
)
from app.domain.ingestion.service import IngestionService
from app.infra.llm import llm_provider
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])


async def _require_admin(user: User = Depends(get_current_user)) -> User:
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


@router.get(
    "/providers",
    response_model=list[ProviderInfo],
    summary="List available ingestion providers",
    description="Returns all registered source connectors with their configuration status.",
)
async def list_providers(
    _user: User = Depends(_require_admin),
) -> list[ProviderInfo]:
    """List all registered ingestion source providers."""
    from app.domain.ingestion.registry import get_all_connectors

    return [
        ProviderInfo(key=key, label=cls().label, configured=cls.is_configured())
        for key, cls in get_all_connectors().items()
    ]


@router.post(
    "/trigger",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a new ingestion job",
    description="Starts ingesting files from a configured source into the base Knowledge Graph. Admin only.",
)
async def trigger_ingestion(
    request: TriggerIngestionRequest = TriggerIngestionRequest(),
    user: User = Depends(_require_admin),
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
    "/stats",
    response_model=IngestionStatsResponse,
    summary="Get aggregate ingestion statistics",
)
async def get_ingestion_stats(
    _user: User = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionStatsResponse:
    """Get aggregate statistics for all ingestion jobs."""
    return await service.get_stats()


@router.get(
    "/cost",
    summary="Get LLM cost and token usage summary",
    description="Returns accumulated LLM token usage and estimated cost since last server restart. Admin only.",
)
async def get_cost_summary(
    _user: User = Depends(_require_admin),
) -> dict:
    """Get accumulated LLM cost and token usage (aggregated across all workers via Redis)."""
    return await llm_provider.get_cost_summary_from_redis()


@router.get(
    "/jobs",
    response_model=IngestionJobListResponse,
    summary="List ingestion jobs",
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    _user: User = Depends(_require_admin),
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
    _user: User = Depends(_require_admin),
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
    _user: User = Depends(_require_admin),
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


@router.post(
    "/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed or cancelled ingestion job",
    description="Resumes processing from where it left off — only retries files that failed or weren't processed.",
)
async def retry_job(
    job_id: uuid.UUID,
    user: User = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> IngestionJobResponse:
    """Retry a failed or cancelled ingestion job."""
    try:
        return await service.retry_job(job_id, admin_user_id=user.id)
    except IngestionJobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        ) from e
    except IngestionAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        ) from e
    except IngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e


# ── Drive folder browsing ─────────────────────────────────────────────────


@router.get(
    "/drive/browse",
    response_model=list[DriveFolderEntry],
    summary="Browse Drive folders",
    description="List subfolders of a Drive folder. Use parent_id='root' for top-level.",
)
async def browse_drive_folders(
    parent_id: str = Query("root", description="Parent folder ID ('root' for top-level)"),
    user: User = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> list[DriveFolderEntry]:
    """List subfolders of a Google Drive folder.

    Uses the logged-in user's OAuth tokens to browse their personal Drive.
    Falls back to server-level credentials when no per-user tokens exist.
    """
    try:
        return await service.browse_drive_folders(parent_id, user_id=user.id)
    except Exception as e:
        logger.error("Failed to browse Drive folders: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to browse Drive: {e}",
        ) from e


@router.get(
    "/drive/default-folder",
    response_model=DefaultFolderResponse,
    summary="Get default Drive folder",
)
async def get_default_folder(
    _user: User = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> DefaultFolderResponse:
    """Get the saved default Drive folder for ingestion."""
    return await service.get_default_folder()


@router.put(
    "/drive/default-folder",
    response_model=DefaultFolderResponse,
    summary="Save default Drive folder",
)
async def save_default_folder(
    request: SaveDefaultFolderRequest,
    _user: User = Depends(_require_admin),
    service: IngestionService = Depends(_get_service),
) -> DefaultFolderResponse:
    """Save/update the default Drive folder for ingestion."""
    return await service.save_default_folder(request.folder_id, request.folder_name)


# ── User-facing Drive browsing (for chat attachments) ─────────────────────


@router.get(
    "/drive/browse-files",
    response_model=list[DriveBrowseEntry],
    summary="Browse Drive files for attachments",
    description=(
        "Browse files and folders in the user's connected Google Drive. "
        "Returns files filtered to supported attachment types plus all folders."
    ),
)
async def browse_drive_for_attachments(
    folder_id: str | None = Query(None, description="Drive folder ID. None = root."),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DriveBrowseEntry]:
    """Browse files and folders in the user's connected Google Drive.

    Returns files filtered to supported attachment types plus all folders
    for navigation. Available to any authenticated user (not admin-only).
    """
    from sqlalchemy import select as sa_select

    from app.domain.auth.models import OAuthAccount

    result = await db.execute(
        sa_select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "google",
        )
    )
    oauth = result.scalar_one_or_none()
    if not oauth:
        raise HTTPException(
            status_code=400,
            detail="Google Drive not connected. Please connect your Google account in settings.",
        )

    from app.domain.ingestion.drive_connector import GoogleDriveConnector
    from app.infra.encryption import decrypt_value

    if not oauth.access_token_enc:
        raise HTTPException(
            status_code=401,
            detail="Google OAuth access token is missing. Please reconnect your Google account.",
        )

    from app.infra.encryption import decrypt_value

    connector = GoogleDriveConnector.from_user_tokens(
        access_token=decrypt_value(oauth.access_token_enc),
        refresh_token=decrypt_value(oauth.refresh_token_enc) if oauth.refresh_token_enc else None,
    )

    ATTACHMENT_MIME_TYPES = {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "text/plain",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.google-apps.document",  # Google Docs (exportable)
    }

    try:
        target_folder = folder_id or "root"
        entries = await connector.list_folder_children(target_folder)

        browse_entries = []
        for entry in entries:
            if entry.is_folder or entry.mime_type in ATTACHMENT_MIME_TYPES:
                browse_entries.append(
                    DriveBrowseEntry(
                        id=entry.file_id,
                        name=entry.name,
                        mime_type=entry.mime_type,
                        size=entry.size,
                        is_folder=entry.is_folder,
                        modified_time=entry.modified_time,
                    )
                )

        return browse_entries
    except Exception as e:
        logger.exception("Failed to browse Drive")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to browse Drive: {e}",
        ) from e
