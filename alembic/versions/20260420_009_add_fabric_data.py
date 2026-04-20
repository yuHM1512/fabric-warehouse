"""add fabric data

Revision ID: 20260420_009
Revises: 20260420_008
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_009"
down_revision = "20260420_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fabric_data",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_model", sa.String(length=64), nullable=False),
        sa.Column("ten_model", sa.String(length=255), nullable=True),
        sa.Column("ghi_chu", sa.String(length=500), nullable=True),
        sa.Column("yrd_per_pallet", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("usd_per_yrd", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fabric_data_ma_model", "fabric_data", ["ma_model"], unique=True)
    op.create_index("ix_fabric_data_yrd_per_pallet", "fabric_data", ["yrd_per_pallet"], unique=False)
    op.create_index("ix_fabric_data_updated_at", "fabric_data", ["updated_at"], unique=False)
    op.create_index("ix_fabric_data_raw_gin", "fabric_data", ["raw_data"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_fabric_data_raw_gin", table_name="fabric_data")
    op.drop_index("ix_fabric_data_updated_at", table_name="fabric_data")
    op.drop_index("ix_fabric_data_yrd_per_pallet", table_name="fabric_data")
    op.drop_index("ix_fabric_data_ma_model", table_name="fabric_data")
    op.drop_table("fabric_data")

