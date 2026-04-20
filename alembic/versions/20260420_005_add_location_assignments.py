"""add location assignments

Revision ID: 20260420_005
Revises: 20260420_004
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_005"
down_revision = "20260420_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=False),
        sa.Column("lot", sa.String(length=64), nullable=False),
        sa.Column("anh_mau", sa.String(length=64), nullable=True),
        sa.Column("vi_tri", sa.String(length=16), nullable=False),
        sa.Column("trang_thai", sa.String(length=32), nullable=False, server_default=sa.text("'Đang lưu'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_location_assignments_ma_cay", "location_assignments", ["ma_cay"], unique=True)
    op.create_index("ix_location_assignments_nhu_cau", "location_assignments", ["nhu_cau"], unique=False)
    op.create_index("ix_location_assignments_lot", "location_assignments", ["lot"], unique=False)
    op.create_index("ix_location_assignments_anh_mau", "location_assignments", ["anh_mau"], unique=False)
    op.create_index("ix_location_assignments_vi_tri", "location_assignments", ["vi_tri"], unique=False)
    op.create_index("ix_location_assignments_trang_thai", "location_assignments", ["trang_thai"], unique=False)
    op.create_index(
        "ix_location_assignments_nhu_cau_lot",
        "location_assignments",
        ["nhu_cau", "lot"],
        unique=False,
    )
    op.create_index(
        "ix_location_assignments_vi_tri_trang_thai",
        "location_assignments",
        ["vi_tri", "trang_thai"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_location_assignments_vi_tri_trang_thai", table_name="location_assignments")
    op.drop_index("ix_location_assignments_nhu_cau_lot", table_name="location_assignments")
    op.drop_index("ix_location_assignments_trang_thai", table_name="location_assignments")
    op.drop_index("ix_location_assignments_vi_tri", table_name="location_assignments")
    op.drop_index("ix_location_assignments_anh_mau", table_name="location_assignments")
    op.drop_index("ix_location_assignments_lot", table_name="location_assignments")
    op.drop_index("ix_location_assignments_nhu_cau", table_name="location_assignments")
    op.drop_index("ix_location_assignments_ma_cay", table_name="location_assignments")
    op.drop_table("location_assignments")

