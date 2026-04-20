"""add transfer logs

Revision ID: 20260420_008
Revises: 20260420_007
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_008"
down_revision = "20260420_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demand_transfer_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("from_nhu_cau", sa.String(length=64), nullable=True),
        sa.Column("from_lot", sa.String(length=64), nullable=True),
        sa.Column("to_nhu_cau", sa.String(length=64), nullable=False),
        sa.Column("to_lot", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_demand_transfer_logs_ma_cay", "demand_transfer_logs", ["ma_cay"], unique=False)
    op.create_index("ix_demand_transfer_logs_from_nhu_cau", "demand_transfer_logs", ["from_nhu_cau"], unique=False)
    op.create_index("ix_demand_transfer_logs_from_lot", "demand_transfer_logs", ["from_lot"], unique=False)
    op.create_index("ix_demand_transfer_logs_to_nhu_cau", "demand_transfer_logs", ["to_nhu_cau"], unique=False)
    op.create_index("ix_demand_transfer_logs_to_lot", "demand_transfer_logs", ["to_lot"], unique=False)
    op.create_index("ix_demand_transfer_logs_created_at", "demand_transfer_logs", ["created_at"], unique=False)
    op.create_index(
        "ix_demand_transfer_logs_ma_cay_created_at",
        "demand_transfer_logs",
        ["ma_cay", "created_at"],
        unique=False,
    )

    op.create_table(
        "location_transfer_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=True),
        sa.Column("lot", sa.String(length=64), nullable=True),
        sa.Column("from_vi_tri", sa.String(length=16), nullable=True),
        sa.Column("to_vi_tri", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_location_transfer_logs_ma_cay", "location_transfer_logs", ["ma_cay"], unique=False)
    op.create_index("ix_location_transfer_logs_nhu_cau", "location_transfer_logs", ["nhu_cau"], unique=False)
    op.create_index("ix_location_transfer_logs_lot", "location_transfer_logs", ["lot"], unique=False)
    op.create_index("ix_location_transfer_logs_from_vi_tri", "location_transfer_logs", ["from_vi_tri"], unique=False)
    op.create_index("ix_location_transfer_logs_to_vi_tri", "location_transfer_logs", ["to_vi_tri"], unique=False)
    op.create_index("ix_location_transfer_logs_created_at", "location_transfer_logs", ["created_at"], unique=False)
    op.create_index(
        "ix_location_transfer_logs_ma_cay_created_at",
        "location_transfer_logs",
        ["ma_cay", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_location_transfer_logs_ma_cay_created_at", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_created_at", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_to_vi_tri", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_from_vi_tri", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_lot", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_nhu_cau", table_name="location_transfer_logs")
    op.drop_index("ix_location_transfer_logs_ma_cay", table_name="location_transfer_logs")
    op.drop_table("location_transfer_logs")

    op.drop_index("ix_demand_transfer_logs_ma_cay_created_at", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_created_at", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_to_lot", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_to_nhu_cau", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_from_lot", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_from_nhu_cau", table_name="demand_transfer_logs")
    op.drop_index("ix_demand_transfer_logs_ma_cay", table_name="demand_transfer_logs")
    op.drop_table("demand_transfer_logs")

