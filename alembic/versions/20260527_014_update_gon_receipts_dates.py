"""update gon receipts dates

Revision ID: 20260527_014
Revises: 20260527_013
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_014"
down_revision = "20260527_013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gon_receipts", sa.Column("ngay_nhap", sa.Date(), nullable=True))
    op.create_index("ix_gon_receipts_ngay_nhap", "gon_receipts", ["ngay_nhap"], unique=False)
    op.drop_column("gon_receipts", "so_kien")
    op.drop_column("gon_receipts", "so_luong")


def downgrade() -> None:
    op.add_column("gon_receipts", sa.Column("so_luong", sa.Numeric(12, 2), nullable=True))
    op.add_column("gon_receipts", sa.Column("so_kien", sa.Integer(), nullable=True))
    op.drop_index("ix_gon_receipts_ngay_nhap", table_name="gon_receipts")
    op.drop_column("gon_receipts", "ngay_nhap")
