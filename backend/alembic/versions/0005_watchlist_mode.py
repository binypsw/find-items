"""Add watchlist_mode and last_watchlist_run_at to saved_searches

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "saved_searches",
        sa.Column(
            "watchlist_mode",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "saved_searches",
        sa.Column(
            "last_watchlist_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_saved_searches_watchlist_mode",
        "saved_searches",
        ["watchlist_mode"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_searches_watchlist_mode", table_name="saved_searches")
    op.drop_column("saved_searches", "last_watchlist_run_at")
    op.drop_column("saved_searches", "watchlist_mode")
