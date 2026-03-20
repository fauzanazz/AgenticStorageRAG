"""Add indexed_files table for two-phase ingestion.

Phase 1 (scanner) writes discovered files here; Phase 2 (processor) reads
pending rows and ingests them sequentially. Provides per-file status
tracking and crash recovery.

Revision ID: f6e5d4c3b2a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "f6e5d4c3b2a1"
down_revision = ("a1b2c3d4e5f6", "e5f7a9b1c3d4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "indexed_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drive_file_id", sa.String(200), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("folder_path", sa.String(2000), nullable=False, server_default=""),
        sa.Column("classification", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", "drive_file_id", name="uq_indexed_file_per_job"),
    )
    op.create_index("ix_indexed_files_job_status", "indexed_files", ["job_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_indexed_files_job_status")
    op.drop_table("indexed_files")
