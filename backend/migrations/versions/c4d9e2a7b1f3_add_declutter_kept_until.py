"""declutter review: date until which a kept item stays out of the review

Revision ID: c4d9e2a7b1f3
Revises: b8f1c2d3e4a5
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d9e2a7b1f3"
down_revision: str | None = "b8f1c2d3e4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("declutter_kept_until", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("clothing_items", "declutter_kept_until")
