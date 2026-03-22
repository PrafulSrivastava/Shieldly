"""add tracking_token to incidents

Revision ID: c5d8e3f2a1b9
Revises: 8b2c4a9f3e01
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union

import secrets
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d8e3f2a1b9"
down_revision: Union[str, None] = "8b2c4a9f3e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first so existing rows can be backfilled
    op.add_column(
        "incidents",
        sa.Column("tracking_token", sa.String(), nullable=True),
    )

    # Backfill existing rows with unique tokens
    conn = op.get_bind()
    incidents = conn.execute(
        sa.text("SELECT id FROM incidents WHERE tracking_token IS NULL")
    )
    for row in incidents:
        conn.execute(
            sa.text("UPDATE incidents SET tracking_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(32), "id": row[0]},
        )

    # Now make it NOT NULL with unique index
    op.alter_column("incidents", "tracking_token", nullable=False)
    op.create_index(
        "ix_incidents_tracking_token", "incidents", ["tracking_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_tracking_token", table_name="incidents")
    op.drop_column("incidents", "tracking_token")
