"""Ingestion domain models.

SQLAlchemy models for tracking ingestion jobs and their progress.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class AppConfig(Base):
    """Simple key-value store for application-level configuration."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IngestionStatus(str, enum.Enum):
    """Ingestion job lifecycle states."""

    PENDING = "pending"
    SCANNING = "scanning"  # Scanning Drive for files
    PROCESSING = "processing"  # Processing files
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IndexedFileStatus(str, enum.Enum):
    """Per-file status within an ingestion job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class IndexedFileStage(str, enum.Enum):
    """Per-file pipeline stage tracking."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    KG_EXTRACTING = "kg_extracting"
    KG_DONE = "kg_done"
    FAILED = "failed"
    SKIPPED = "skipped"
    EMBED_FAILED = "embed_failed"
    KG_FAILED = "kg_failed"


class IngestionJob(Base):
    """Tracks a batch ingestion run from a source connector.

    Each job represents one run of the ingestion pipeline, potentially
    processing multiple files from Google Drive.
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid7,
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin user who triggered this job",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="google_drive",
        comment="Source connector type (google_drive, etc.)",
    )
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, name="ingestion_status", create_constraint=True),
        default=IngestionStatus.PENDING,
        nullable=False,
        index=True,
    )
    folder_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Google Drive folder ID to scan (None = root)",
    )
    total_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    processed_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    failed_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    skipped_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Files skipped (already ingested, unsupported type, etc.)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
        comment="Additional job metadata (file list, errors per file, etc.)",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IngestionJob id={self.id} status={self.status} "
            f"processed={self.processed_files}/{self.total_files}>"
        )


class IndexedFile(Base):
    """A file discovered during Phase 1 (scanning) of ingestion.

    Tracks per-file status for resumable Phase 2 processing.
    """

    __tablename__ = "indexed_files"
    __table_args__ = (
        {"comment": "Files discovered by the scanner, processed by the file processor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid7,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    drive_file_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    folder_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    classification: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IndexedFileStatus.PENDING.value,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IndexedFileStage.PENDING.value,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<IndexedFile id={self.id} file={self.file_name} status={self.status}>"
