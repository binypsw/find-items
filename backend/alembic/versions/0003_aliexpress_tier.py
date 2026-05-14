"""Update AliExpress source tier to browser_headless

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE sources SET tier='browser_headless' WHERE id='aliexpress'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sources SET tier='direct' WHERE id='aliexpress'"
    )
