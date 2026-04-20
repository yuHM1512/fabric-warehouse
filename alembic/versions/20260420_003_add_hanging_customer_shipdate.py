"""add customer + ngay_xuat to hanging tags

Revision ID: 20260420_003
Revises: 20260420_002
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_003"
down_revision = "20260420_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hanging_tags", sa.Column("customer", sa.String(length=255), nullable=True))
    op.add_column("hanging_tags", sa.Column("ngay_xuat", sa.Date(), nullable=True))
    op.create_index("ix_hanging_tags_ngay_xuat", "hanging_tags", ["ngay_xuat"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_hanging_tags_ngay_xuat", table_name="hanging_tags")
    op.drop_column("hanging_tags", "ngay_xuat")
    op.drop_column("hanging_tags", "customer")

