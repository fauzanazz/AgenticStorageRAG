"""Add steps_json to messages for ordered step persistence.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("steps_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "steps_json")
