"""add return events

Revision ID: 20260420_007
Revises: 20260420_006
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_007"
down_revision = "20260420_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "return_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("issue_line_id", sa.Integer(), sa.ForeignKey("issue_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("ngay_tai_nhap", sa.Date(), nullable=False),
        sa.Column("yds_du", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("nhu_cau_moi", sa.String(length=64), nullable=True),
        sa.Column("lot_moi", sa.String(length=64), nullable=True),
        sa.Column("vi_tri_moi", sa.String(length=16), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("issue_line_id", name="ux_return_events_issue_line_id"),
    )
    op.create_index("ix_return_events_issue_line_id", "return_events", ["issue_line_id"], unique=True)
    op.create_index("ix_return_events_ma_cay", "return_events", ["ma_cay"], unique=False)
    op.create_index("ix_return_events_ngay_tai_nhap", "return_events", ["ngay_tai_nhap"], unique=False)
    op.create_index("ix_return_events_status", "return_events", ["status"], unique=False)
    op.create_index("ix_return_events_nhu_cau_moi", "return_events", ["nhu_cau_moi"], unique=False)
    op.create_index("ix_return_events_lot_moi", "return_events", ["lot_moi"], unique=False)
    op.create_index("ix_return_events_vi_tri_moi", "return_events", ["vi_tri_moi"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_return_events_vi_tri_moi", table_name="return_events")
    op.drop_index("ix_return_events_lot_moi", table_name="return_events")
    op.drop_index("ix_return_events_nhu_cau_moi", table_name="return_events")
    op.drop_index("ix_return_events_status", table_name="return_events")
    op.drop_index("ix_return_events_ngay_tai_nhap", table_name="return_events")
    op.drop_index("ix_return_events_ma_cay", table_name="return_events")
    op.drop_index("ix_return_events_issue_line_id", table_name="return_events")
    op.drop_table("return_events")

