"""Ingestion domain models.

SQLAlchemy models for tracking ingestion jobs and their progress.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class IngestionStatus(str, enum.Enum):
    """Ingestion job lifecycle states."""

    PENDING = "pending"
    SCANNING = "scanning"        # Scanning Drive for files
    PROCESSING = "processing"    # Processing files
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionJob(Base):
    """Tracks a batch ingestion run from a source connector.

    Each job represents one run of the ingestion swarm, potentially
    processing multiple files from Google Drive.
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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
        default=lambda: datetime.now(timezone.utc),
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
