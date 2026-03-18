"""Documents domain models.

SQLAlchemy models for document management and chunking.
Documents have a 7-day TTL for user uploads; base KG documents are permanent.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database import Base


class DocumentStatus(str, enum.Enum):
    """Document processing lifecycle states."""

    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class DocumentSource(str, enum.Enum):
    """Where the document originated from."""

    UPLOAD = "upload"          # User uploaded via web UI
    GOOGLE_DRIVE = "google_drive"  # Base KG from Google Drive


class Document(Base):
    """A document uploaded or ingested into the system.

    Tracks the full lifecycle from upload → processing → ready → expired.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    file_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="MIME type or extension (e.g., 'application/pdf', 'docx')",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    storage_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Path in Supabase Storage bucket, or 'drive://{file_id}' for Drive-sourced docs",
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", create_constraint=True),
        default=DocumentStatus.UPLOADING,
        nullable=False,
        index=True,
    )
    source: Mapped[DocumentSource] = mapped_column(
        Enum(DocumentSource, name="document_source", create_constraint=True),
        default=DocumentSource.UPLOAD,
        nullable=False,
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if processing failed",
    )
    is_base_knowledge: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True for permanent base KG documents (no TTL)",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
        comment="Extracted metadata (title, author, page count, etc.)",
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="NULL for base KG docs (permanent). Set for user uploads.",
    )

    # Relationships
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename} status={self.status}>"


class DocumentChunk(Base):
    """A chunk of text extracted from a document.

    Used for vector search and as context for RAG responses.
    Each chunk references its source document and location within it.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sequential index of this chunk within the document",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The actual text content of this chunk",
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Page number in the original document (if applicable)",
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of tokens in this chunk (for LLM context budgeting)",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
        comment="Chunk-level metadata (headings, section, etc.)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
