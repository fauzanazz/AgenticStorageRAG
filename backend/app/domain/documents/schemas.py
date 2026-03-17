"""Documents domain Pydantic schemas.

Request/response schemas for the documents API endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""

    id: uuid.UUID
    filename: str
    file_type: str
    file_size: int
    status: str
    uploaded_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Full document response with chunk info."""

    id: uuid.UUID
    filename: str
    file_type: str
    file_size: int
    status: str
    source: str
    chunk_count: int
    error_message: str | None
    is_base_knowledge: bool
    metadata: dict = Field(default_factory=dict, alias="metadata_")
    uploaded_at: datetime
    processed_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentChunkResponse(BaseModel):
    """Single chunk response."""

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None
    token_count: int
    metadata: dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class ProcessingResult(BaseModel):
    """Result of processing a document through a processor."""

    chunks: list[ChunkData]
    metadata: dict = Field(default_factory=dict)
    page_count: int | None = None
    total_characters: int = 0


class ChunkData(BaseModel):
    """Data for a single chunk extracted by a processor."""

    content: str
    page_number: int | None = None
    chunk_index: int = 0
    metadata: dict = Field(default_factory=dict)


# Fix forward reference
ProcessingResult.model_rebuild()


class DashboardStatsResponse(BaseModel):
    """Aggregated stats for the user dashboard."""

    total_documents: int = 0
    total_chunks: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    total_embeddings: int = 0
    processing_documents: int = 0
