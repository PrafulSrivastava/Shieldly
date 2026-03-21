"""add rejected to shieldstatus enum

Revision ID: a3f9d2e1b4c7
Revises: 1f7e1cc31ac5
Create Date: 2026-03-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9d2e1b4c7"
down_revision: Union[str, None] = "1f7e1cc31ac5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL supports adding enum values non-transactionally.
    # IF NOT EXISTS prevents errors on repeated runs.
    op.execute("ALTER TYPE shieldstatus ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    # PostgreSQL does not support removing individual enum values without
    # recreating the type. A full rollback would require recreating the enum
    # and casting the column — out of scope for this MVP migration.
    pass
