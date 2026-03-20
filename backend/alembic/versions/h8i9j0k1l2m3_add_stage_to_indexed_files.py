"""Add stage and retry_count columns to indexed_files for pipeline tracking.

The stage column tracks per-file progress through the pipeline stages:
pending -> downloading -> downloaded -> extracting -> extracted ->
embedding -> embedded -> kg_extracting -> kg_done

retry_count tracks embed/KG retry attempts.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa

revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "indexed_files",
        sa.Column("stage", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "indexed_files",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Index for efficient polling by the pipeline feeder
    op.create_index(
        "ix_indexed_files_job_stage",
        "indexed_files",
        ["job_id", "stage"],
    )
    # Backfill: completed files should be marked as kg_done
    op.execute(
        "UPDATE indexed_files SET stage = 'kg_done' WHERE status = 'completed'"
    )
    op.execute(
        "UPDATE indexed_files SET stage = 'failed' WHERE status = 'failed'"
    )
    op.execute(
        "UPDATE indexed_files SET stage = 'skipped' WHERE status = 'skipped'"
    )


def downgrade() -> None:
    op.drop_index("ix_indexed_files_job_stage", table_name="indexed_files")
    op.drop_column("indexed_files", "retry_count")
    op.drop_column("indexed_files", "stage")
