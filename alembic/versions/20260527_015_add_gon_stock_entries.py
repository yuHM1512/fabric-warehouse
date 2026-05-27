"""add gon stock entries

Revision ID: 20260527_015
Revises: 20260527_014
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_015"
down_revision = "20260527_014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gon_stock_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gon_type", sa.String(length=255), nullable=False),
        sa.Column("so_kien", sa.Integer(), nullable=False),
        sa.Column("so_yds", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("warehouse_area", sa.String(length=16), nullable=False),
        sa.Column("tang", sa.String(length=8), nullable=True),
        sa.Column("line", sa.String(length=8), nullable=True),
        sa.Column("pallet", sa.String(length=8), nullable=True),
        sa.Column("block", sa.String(length=8), nullable=True),
        sa.Column("vi_tri", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gon_stock_entries_gon_type", "gon_stock_entries", ["gon_type"], unique=False)
    op.create_index("ix_gon_stock_entries_warehouse_area", "gon_stock_entries", ["warehouse_area"], unique=False)
    op.create_index("ix_gon_stock_entries_block", "gon_stock_entries", ["block"], unique=False)
    op.create_index("ix_gon_stock_entries_vi_tri", "gon_stock_entries", ["vi_tri"], unique=False)
    op.create_index("ix_gon_stock_entries_created_at", "gon_stock_entries", ["created_at"], unique=False)
    op.create_index("ix_gon_stock_entries_area_vi_tri", "gon_stock_entries", ["warehouse_area", "vi_tri"], unique=False)
    op.create_index("ix_gon_stock_entries_block_created_at", "gon_stock_entries", ["block", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gon_stock_entries_block_created_at", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_area_vi_tri", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_created_at", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_vi_tri", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_block", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_warehouse_area", table_name="gon_stock_entries")
    op.drop_index("ix_gon_stock_entries_gon_type", table_name="gon_stock_entries")
    op.drop_table("gon_stock_entries")
