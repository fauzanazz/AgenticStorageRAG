"""Add openrouter_api_key_enc to user_model_settings.

Revision ID: a1b2c3d4e5f6
Revises: d4e6f8a0b2c3
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d4e6f8a0b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_model_settings",
        sa.Column("openrouter_api_key_enc", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_model_settings", "openrouter_api_key_enc")
