"""init receipts

Revision ID: 20260420_001
Revises:
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fabric_rolls",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fabric_rolls_ma_cay", "fabric_rolls", ["ma_cay"], unique=True)

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("roll_id", sa.Integer(), sa.ForeignKey("fabric_rolls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=True),
        sa.Column("lot", sa.String(length=64), nullable=True),
        sa.Column("anh_mau", sa.String(length=64), nullable=False, server_default=sa.text("'CHUNG'")),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("art", sa.String(length=64), nullable=True),
        sa.Column("yards", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_receipt_lines_receipt_id", "receipt_lines", ["receipt_id"], unique=False)
    op.create_index("ix_receipt_lines_roll_id", "receipt_lines", ["roll_id"], unique=False)
    op.create_index("ix_receipt_lines_ma_cay", "receipt_lines", ["ma_cay"], unique=False)
    op.create_index("ix_receipt_lines_nhu_cau", "receipt_lines", ["nhu_cau"], unique=False)
    op.create_index("ix_receipt_lines_lot", "receipt_lines", ["lot"], unique=False)
    op.create_index("ix_receipt_lines_anh_mau", "receipt_lines", ["anh_mau"], unique=False)
    op.create_index("ix_receipt_lines_model", "receipt_lines", ["model"], unique=False)
    op.create_index("ix_receipt_lines_art", "receipt_lines", ["art"], unique=False)

    op.create_index(
        "ix_receipt_lines_receipt_ma_cay",
        "receipt_lines",
        ["receipt_id", "ma_cay"],
        unique=True,
    )
    op.create_index(
        "ix_receipt_lines_receipt_nhu_cau_lot",
        "receipt_lines",
        ["receipt_id", "nhu_cau", "lot"],
        unique=False,
    )
    op.create_index(
        "ix_receipt_lines_roll_id_receipt_id",
        "receipt_lines",
        ["roll_id", "receipt_id"],
        unique=False,
    )
    op.create_index(
        "ix_receipt_lines_raw_gin",
        "receipt_lines",
        ["raw_data"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_receipt_lines_raw_gin", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_roll_id_receipt_id", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_receipt_nhu_cau_lot", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_receipt_ma_cay", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_art", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_model", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_anh_mau", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_lot", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_nhu_cau", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_ma_cay", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_roll_id", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_receipt_id", table_name="receipt_lines")
    op.drop_table("receipt_lines")
    op.drop_table("receipts")

    op.drop_index("ix_fabric_rolls_ma_cay", table_name="fabric_rolls")
    op.drop_table("fabric_rolls")

