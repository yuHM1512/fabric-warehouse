"""add gon receipts

Revision ID: 20260527_013
Revises: 20260424_012
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_013"
down_revision = "20260424_012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gon_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nha_cung_cap", sa.String(length=255), nullable=True),
        sa.Column("ten_gon", sa.String(length=255), nullable=False),
        sa.Column("quy_cach", sa.String(length=255), nullable=True),
        sa.Column("ma_hang", sa.String(length=64), nullable=True),
        sa.Column("mua", sa.String(length=64), nullable=True),
        sa.Column("so_luong", sa.Numeric(12, 2), nullable=True),
        sa.Column("so_kien", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gon_receipts_ma_hang", "gon_receipts", ["ma_hang"], unique=False)
    op.create_index("ix_gon_receipts_mua", "gon_receipts", ["mua"], unique=False)
    op.create_index(
        "ix_gon_receipts_supplier_item",
        "gon_receipts",
        ["nha_cung_cap", "ma_hang"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gon_receipts_supplier_item", table_name="gon_receipts")
    op.drop_index("ix_gon_receipts_mua", table_name="gon_receipts")
    op.drop_index("ix_gon_receipts_ma_hang", table_name="gon_receipts")
    op.drop_table("gon_receipts")
