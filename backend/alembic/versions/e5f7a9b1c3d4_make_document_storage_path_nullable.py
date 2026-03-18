"""make_document_storage_path_nullable

Drive-sourced documents no longer copy files to Supabase Storage.
Instead they store a logical reference ("drive://{file_id}") in storage_path.
Making the column nullable also future-proofs for other sources that may not
have a Supabase-backed binary.

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a0b2c3
Create Date: 2026-03-18
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f7a9b1c3d4"
down_revision = "d4e6f8a0b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("documents", "storage_path", nullable=True)


def downgrade() -> None:
    # Rows with NULL storage_path (Drive docs) must be back-filled before
    # reverting; this migration sets them to an empty string as a safe fallback.
    op.execute(
        "UPDATE documents SET storage_path = '' WHERE storage_path IS NULL"
    )
    op.alter_column("documents", "storage_path", nullable=False)
