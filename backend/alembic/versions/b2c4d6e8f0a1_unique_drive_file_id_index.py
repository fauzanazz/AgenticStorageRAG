"""Add partial unique index on drive_file_id to prevent duplicate ingestion.

Without this, two concurrent ingestion runs (or an LLM agent calling ingest_file
twice for the same file_id) could insert duplicate Document rows because
drive_file_id lives inside a JSONB blob and has no DB-level uniqueness constraint.

The partial index covers only Google Drive base-knowledge documents in READY
status, which is exactly the population that _filter_new_files() / IngestFileTool
intend to deduplicate against.

Revision ID: b2c4d6e8f0a1
Revises: a538f73ff58d
Create Date: 2026-03-18
"""

from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, None] = "a538f73ff58d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique expression index on the JSONB drive_file_id key.
    # Only applies to Google Drive base-knowledge documents that are READY,
    # so it doesn't block the in-flight PROCESSING rows that are later marked
    # READY by the same job run.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_documents_drive_file_id
        ON documents ((metadata->>'drive_file_id'))
        WHERE source = 'GOOGLE_DRIVE'
          AND is_base_knowledge = TRUE
          AND status = 'READY';
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_documents_drive_file_id;")
