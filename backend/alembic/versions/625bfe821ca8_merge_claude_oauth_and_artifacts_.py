"""merge claude_oauth and artifacts branches

Revision ID: 625bfe821ca8
Revises: f1a2b3c4d5e6, i9j0k1l2m3n4
Create Date: 2026-03-20 17:11:50.143535
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '625bfe821ca8'
down_revision: Union[str, None] = ('f1a2b3c4d5e6', 'i9j0k1l2m3n4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
