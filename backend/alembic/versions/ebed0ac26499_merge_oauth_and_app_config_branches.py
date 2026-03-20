"""merge oauth and app_config branches

Revision ID: ebed0ac26499
Revises: e5f7a9b1c3d5, h8i9j0k1l2m3
Create Date: 2026-03-20 04:16:44.454512
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebed0ac26499'
down_revision: Union[str, None] = ('e5f7a9b1c3d5', 'h8i9j0k1l2m3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
