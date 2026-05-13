"""Fix stale browserless tier values in sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # shopee and lazada use Playwright headless — not browserless
    op.execute(
        "UPDATE sources SET tier='browser_headless' "
        "WHERE id IN ('shopee', 'lazada') AND tier='browserless'"
    )
    # aliexpress has no plugin yet — direct is the roadmap approach
    op.execute(
        "UPDATE sources SET tier='direct' "
        "WHERE id = 'aliexpress' AND tier='browserless'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sources SET tier='browserless' "
        "WHERE id IN ('shopee', 'lazada') AND tier='browser_headless'"
    )
    op.execute(
        "UPDATE sources SET tier='browserless' "
        "WHERE id = 'aliexpress' AND tier='direct'"
    )
