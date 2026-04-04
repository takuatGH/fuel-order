"""add pending_acceptance to driver_status enum

Revision ID: 20260402_driver_pending_acceptance
Revises: 20260401_add_delivery_address
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260402_pending_accept"
down_revision: Union[str, None] = "20260401_add_delivery_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE driver_status ADD VALUE IF NOT EXISTS 'pending_acceptance'")


def downgrade() -> None:
    pass  # postgres cannot remove enum values
