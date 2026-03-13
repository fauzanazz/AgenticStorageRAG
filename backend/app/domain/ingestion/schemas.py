"""Ingestion domain schemas.

Pydantic request/response models for the ingestion API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TriggerIngestionRequest(BaseModel):
    """Request to trigger a new ingestion job."""

    folder_id: str | None = Field(
        default=None,
        description="Google Drive folder ID. None = scan root.",
    )
    force: bool = Field(
        default=False,
        description="Re-ingest files even if already processed.",
    )


class IngestionJobResponse(BaseModel):
    """Response for an ingestion job."""

    id: uuid.UUID
    source: str
    status: str
    folder_id: str | None
    total_files: int
    processed_files: int
    failed_files: int
    skipped_files: int
    error_message: str | None
    metadata_: dict = Field(alias="metadata", default_factory=dict)
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True, "populate_by_name": True}


class IngestionJobListResponse(BaseModel):
    """Paginated list of ingestion jobs."""

    items: list[IngestionJobResponse]
    total: int


class DriveFileInfo(BaseModel):
    """Information about a file in Google Drive."""

    file_id: str
    name: str
    mime_type: str
    size: int | None = None
    modified_time: str | None = None
    parent_folder: str | None = None


class IngestionProgressEvent(BaseModel):
    """SSE event for ingestion progress updates."""

    type: str  # "scanning", "processing", "file_done", "error", "complete"
    message: str
    file_name: str | None = None
    progress: float | None = None  # 0.0 - 1.0
    job_id: uuid.UUID | None = None
