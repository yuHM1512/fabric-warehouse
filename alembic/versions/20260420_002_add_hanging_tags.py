"""add hanging tags

Revision ID: 20260420_002
Revises: 20260420_001
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_002"
down_revision = "20260420_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hanging_tags",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_bang_treo", sa.String(length=255), nullable=False),
        sa.Column("ngay_nhap_hang", sa.Date(), nullable=True),
        sa.Column("nhu_cau", sa.String(length=64), nullable=True),
        sa.Column("lot", sa.String(length=64), nullable=True),
        sa.Column("ma_hang", sa.String(length=32), nullable=True),
        sa.Column("nha_cung_cap", sa.String(length=255), nullable=True),
        sa.Column("khach_hang", sa.String(length=255), nullable=True),
        sa.Column("loai_vai", sa.String(length=500), nullable=True),
        sa.Column("ma_art", sa.String(length=64), nullable=True),
        sa.Column("mau_vai", sa.String(length=255), nullable=True),
        sa.Column("ma_mau", sa.String(length=64), nullable=True),
        sa.Column("ket_qua_kiem_tra", sa.String(length=64), nullable=True, server_default=sa.text("'OK'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_hanging_tags_receipt_id", "hanging_tags", ["receipt_id"], unique=False)
    op.create_index("ix_hanging_tags_id_bang_treo", "hanging_tags", ["id_bang_treo"], unique=True)
    op.create_index("ix_hanging_tags_ngay_nhap_hang", "hanging_tags", ["ngay_nhap_hang"], unique=False)
    op.create_index("ix_hanging_tags_nhu_cau", "hanging_tags", ["nhu_cau"], unique=False)
    op.create_index("ix_hanging_tags_lot", "hanging_tags", ["lot"], unique=False)
    op.create_index("ix_hanging_tags_ma_hang", "hanging_tags", ["ma_hang"], unique=False)
    op.create_index("ix_hanging_tags_ma_art", "hanging_tags", ["ma_art"], unique=False)
    op.create_index(
        "ix_hanging_tags_receipt_nhu_cau_lot",
        "hanging_tags",
        ["receipt_id", "nhu_cau", "lot"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_hanging_tags_receipt_nhu_cau_lot", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_ma_art", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_ma_hang", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_lot", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_nhu_cau", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_ngay_nhap_hang", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_id_bang_treo", table_name="hanging_tags")
    op.drop_index("ix_hanging_tags_receipt_id", table_name="hanging_tags")
    op.drop_table("hanging_tags")

