"""Add oauth_accounts table and make hashed_password nullable.

Supports OAuth login (Google, etc.) by storing provider tokens per user.
Users who sign in exclusively via OAuth will have a NULL hashed_password.

Revision ID: g7h8i9j0k1l2
Revises: f6e5d4c3b2a1
Create Date: 2026-03-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: str | None = "f6e5d4c3b2a1"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Allow OAuth-only users (no password)
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )
    op.create_index(
        op.f("ix_oauth_accounts_user_id"),
        "oauth_accounts",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_oauth_accounts_user_id"),
        table_name="oauth_accounts",
    )
    op.drop_table("oauth_accounts")

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.Text(),
        nullable=False,
    )
