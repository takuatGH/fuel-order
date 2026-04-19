"""add owner_id to depots

Revision ID: 20260419_add_depot_owner_id
Revises: 20260402_pending_accept
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260419_add_depot_owner_id"
down_revision: Union[str, None] = "20260402_pending_accept"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "depots",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("depots", "owner_id")
