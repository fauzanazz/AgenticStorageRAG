"""Add user_model_settings table for per-user LLM configuration.

Each user can store their own API keys (Fernet-encrypted) and preferred
model selections for chat, ingestion, and embedding operations.

Revision ID: c3d5e7f9a1b2
Revises: b2c4d6e8f0a1
Create Date: 2026-03-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d5e7f9a1b2"
down_revision: str | None = "b2c4d6e8f0a1"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "user_model_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "chat_model",
            sa.String(length=200),
            nullable=False,
            server_default="dashscope/qwen3-max",
        ),
        sa.Column(
            "ingestion_model",
            sa.String(length=200),
            nullable=False,
            server_default="dashscope/qwen3-max",
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=200),
            nullable=False,
            server_default="openai/text-embedding-3-small",
        ),
        sa.Column("anthropic_api_key_enc", sa.Text(), nullable=True),
        sa.Column("openai_api_key_enc", sa.Text(), nullable=True),
        sa.Column("dashscope_api_key_enc", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_user_model_settings_user_id"),
        "user_model_settings",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_model_settings_user_id"),
        table_name="user_model_settings",
    )
    op.drop_table("user_model_settings")
