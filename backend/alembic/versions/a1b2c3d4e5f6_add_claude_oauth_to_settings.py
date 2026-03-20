"""add claude oauth to user_model_settings

Revision ID: a1b2c3d4e5f6
Revises: d5f7a9b1c3e4
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "d5f7a9b1c3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_model_settings", sa.Column("claude_oauth_token_enc", sa.Text(), nullable=True))
    op.add_column("user_model_settings", sa.Column("claude_oauth_refresh_token_enc", sa.Text(), nullable=True))
    op.add_column("user_model_settings", sa.Column("claude_oauth_token_expiry", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_model_settings", "claude_oauth_token_expiry")
    op.drop_column("user_model_settings", "claude_oauth_refresh_token_enc")
    op.drop_column("user_model_settings", "claude_oauth_token_enc")
