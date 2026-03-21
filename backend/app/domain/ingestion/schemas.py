"""Ingestion domain schemas.

Pydantic request/response models for the ingestion API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TriggerIngestionRequest(BaseModel):
    """Request to trigger a new ingestion job."""

    source: str = Field(
        default="google_drive",
        description="Source connector key (e.g. 'google_drive').",
    )
    folder_id: str | None = Field(
        default=None,
        description="Google Drive folder ID. None = scan root.",
    )
    force: bool = Field(
        default=False,
        description="Re-ingest files even if already processed.",
    )


class ProviderInfo(BaseModel):
    """Describes an available ingestion source provider."""

    key: str
    label: str
    configured: bool


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
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_")
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True, "populate_by_name": True}


class IngestionJobListResponse(BaseModel):
    """Paginated list of ingestion jobs."""

    items: list[IngestionJobResponse]
    total: int


class IngestionStatsResponse(BaseModel):
    """Aggregate statistics for all ingestion jobs."""

    total_jobs: int
    jobs_by_status: dict[str, int]
    total_files_processed: int
    total_files_failed: int
    total_files_skipped: int
    active_job: IngestionJobResponse | None = None


class DriveFileInfo(BaseModel):
    """Information about a file in Google Drive."""

    file_id: str
    name: str
    mime_type: str
    size: int | None = None
    modified_time: str | None = None
    parent_folder: str | None = None


class DriveFolderEntry(BaseModel):
    """A single item (file or subfolder) inside a Drive folder."""

    file_id: str
    name: str
    mime_type: str
    size: int | None = None
    modified_time: str | None = None
    is_folder: bool = False
    target_id: str | None = None  # resolved shortcut target


class DefaultFolderResponse(BaseModel):
    """Saved default Drive folder for ingestion."""

    folder_id: str | None = None
    folder_name: str | None = None


class SaveDefaultFolderRequest(BaseModel):
    """Request to save/update the default Drive folder."""

    folder_id: str = Field(description="Google Drive folder ID")
    folder_name: str = Field(description="Folder display name")


class FileMetadataClassification(BaseModel):
    """LLM-classified metadata extracted from a file's folder path context.

    Not rule-based -- the LLM infers these fields from the raw folder path
    so it adapts to any folder structure.
    """

    folder_path: str = Field(
        description="Raw folder breadcrumb, e.g. 'Informatika/Semester 3/IF2120 - Probabilitas dan Statistika/Referensi'",
    )
    major: str | None = Field(default=None, description="Academic major or department")
    course_code: str | None = Field(default=None, description="Course code, e.g. IF2120")
    course_name: str | None = Field(
        default=None, description="Course name, e.g. Probabilitas dan Statistika"
    )
    year: str | None = Field(default=None, description="Academic year or curriculum year")
    category: str | None = Field(
        default=None,
        description="Content category: Referensi, Slide, Soal, Catatan, etc.",
    )
    additional_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Any other LLM-extracted fields that don't fit the above",
    )


class EnrichedFileInfo(DriveFileInfo):
    """DriveFileInfo enriched with folder context and LLM classification."""

    folder_path: str = ""
    folder_path_ids: list[str] = Field(default_factory=list)
    classification: FileMetadataClassification | None = None


class DriveBrowseEntry(BaseModel):
    """A file or folder entry from Google Drive browsing (user-facing)."""

    id: str
    name: str
    mime_type: str
    size: int | None = None
    is_folder: bool = False
    modified_time: str | None = None


class IngestionProgressEvent(BaseModel):
    """SSE event for ingestion progress updates."""

    type: str  # "scanning", "processing", "file_done", "error", "complete"
    message: str
    file_name: str | None = None
    progress: float | None = None  # 0.0 - 1.0
    job_id: uuid.UUID | None = None
    current_folder: str | None = None
    files_discovered: int | None = None
    files_classified: int | None = None
