"""add stock checks

Revision ID: 20260420_004
Revises: 20260420_003
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_004"
down_revision = "20260420_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_checks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=False),
        sa.Column("lot", sa.String(length=64), nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("expected_yards", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("actual_yards", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_stock_checks_nhu_cau", "stock_checks", ["nhu_cau"], unique=False)
    op.create_index("ix_stock_checks_lot", "stock_checks", ["lot"], unique=False)
    op.create_index("ix_stock_checks_ma_cay", "stock_checks", ["ma_cay"], unique=False)
    op.create_index("ix_stock_checks_nhu_cau_lot", "stock_checks", ["nhu_cau", "lot"], unique=False)
    op.create_index("ux_stock_checks_key", "stock_checks", ["nhu_cau", "lot", "ma_cay"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_stock_checks_key", table_name="stock_checks")
    op.drop_index("ix_stock_checks_nhu_cau_lot", table_name="stock_checks")
    op.drop_index("ix_stock_checks_ma_cay", table_name="stock_checks")
    op.drop_index("ix_stock_checks_lot", table_name="stock_checks")
    op.drop_index("ix_stock_checks_nhu_cau", table_name="stock_checks")
    op.drop_table("stock_checks")

