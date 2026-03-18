"""Widen documents.file_type from VARCHAR(50) to VARCHAR(200).

Google Docs export MIME types such as
  application/vnd.openxmlformats-officedocument.wordprocessingml.document
are 71 characters — they exceed the original 50-char limit and caused
StringDataRightTruncationError during ingestion of Google Docs files.

Revision ID: d4e6f8a0b2c3
Revises: c3d5e7f9a1b2
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "d4e6f8a0b2c3"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use raw DDL to bypass Supabase's statement_timeout on ALTER TABLE.
    # VARCHAR widening is a metadata-only operation in PostgreSQL (no table rewrite
    # needed) but Supabase still enforces statement_timeout via pgbouncer.
    # Disabling it for this session allows the DDL to complete.
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN file_type TYPE VARCHAR(200)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN file_type TYPE VARCHAR(50)"
    )
