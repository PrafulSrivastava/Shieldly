"""add expo_push_token to shields

Revision ID: 8b2c4a9f3e01
Revises: a3f9d2e1b4c7
Create Date: 2026-03-21 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b2c4a9f3e01"
down_revision: Union[str, None] = "a3f9d2e1b4c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shields", sa.Column("expo_push_token", sa.String(), nullable=True))
    op.add_column(
        "shields",
        sa.Column("token_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shields", "token_updated_at")
    op.drop_column("shields", "expo_push_token")
