"""nepse_broker member master

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-16

Broker names for every nepse_floorsheet session: merolagani's floor-sheet
history (all sessions before live collection) carries member codes only,
and NEPSE publishes names only in its own latest-session floor sheet. The
official member list maps every code to its current registered name.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nepse_broker",
        sa.Column("member_code", sa.Integer(), primary_key=True),
        sa.Column("member_name", sa.Text(), nullable=False),
        sa.Column("active_status", sa.Text(), nullable=True),
        sa.Column("membership_type", sa.Text(), nullable=True),
        sa.Column("is_dealer", sa.Boolean(), nullable=True),
        sa.Column("nepse_member_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("nepse_broker")
