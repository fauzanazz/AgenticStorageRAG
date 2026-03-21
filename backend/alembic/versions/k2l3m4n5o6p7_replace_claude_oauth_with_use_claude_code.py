"""Replace Claude OAuth columns with use_claude_code boolean.

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "k2l3m4n5o6p7"
down_revision = "j1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_model_settings",
        sa.Column("use_claude_code", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.drop_column("user_model_settings", "claude_oauth_token_enc")
    op.drop_column("user_model_settings", "claude_oauth_refresh_token_enc")
    op.drop_column("user_model_settings", "claude_oauth_token_expiry")


def downgrade() -> None:
    op.add_column(
        "user_model_settings",
        sa.Column("claude_oauth_token_expiry", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_model_settings",
        sa.Column("claude_oauth_refresh_token_enc", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_model_settings",
        sa.Column("claude_oauth_token_enc", sa.Text(), nullable=True),
    )
    op.drop_column("user_model_settings", "use_claude_code")
