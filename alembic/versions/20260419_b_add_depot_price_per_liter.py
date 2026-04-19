"""add price_per_liter to depots

Revision ID: 20260419_b_depot_price
Revises: 20260419_add_depot_owner_id
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260419_b_depot_price"
down_revision: Union[str, None] = "20260419_add_depot_owner_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "depots",
        sa.Column("price_per_liter", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("depots", "price_per_liter")
