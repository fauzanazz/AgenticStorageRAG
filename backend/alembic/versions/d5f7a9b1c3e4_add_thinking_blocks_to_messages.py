"""add thinking_blocks to messages

Revision ID: d5f7a9b1c3e4
Revises: ebed0ac26499
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d5f7a9b1c3e4"
down_revision = "ebed0ac26499"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("thinking_blocks_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "thinking_blocks_json")
