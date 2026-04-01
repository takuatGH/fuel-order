"""add delivery_address to orders

Revision ID: 20260401_add_delivery_address
Revises: 20260209_0600_initial_schema
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260401_add_delivery_address"
down_revision: Union[str, None] = "20260209_0600_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "delivery_address")
