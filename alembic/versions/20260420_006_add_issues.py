"""add issues

Revision ID: 20260420_006
Revises: 20260420_005
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_006"
down_revision = "20260420_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=False),
        sa.Column("lot", sa.String(length=64), nullable=False),
        sa.Column("ngay_xuat", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default=sa.text("'Cấp phát sản xuất'")),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_issues_nhu_cau", "issues", ["nhu_cau"], unique=False)
    op.create_index("ix_issues_lot", "issues", ["lot"], unique=False)
    op.create_index("ix_issues_ngay_xuat", "issues", ["ngay_xuat"], unique=False)
    op.create_index("ix_issues_status", "issues", ["status"], unique=False)

    op.create_table(
        "issue_lines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("so_luong_xuat", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("vi_tri", sa.String(length=16), nullable=True),
    )
    op.create_index("ix_issue_lines_issue_id", "issue_lines", ["issue_id"], unique=False)
    op.create_index("ix_issue_lines_ma_cay", "issue_lines", ["ma_cay"], unique=False)
    op.create_index("ix_issue_lines_issue_ma_cay", "issue_lines", ["issue_id", "ma_cay"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_issue_lines_issue_ma_cay", table_name="issue_lines")
    op.drop_index("ix_issue_lines_ma_cay", table_name="issue_lines")
    op.drop_index("ix_issue_lines_issue_id", table_name="issue_lines")
    op.drop_table("issue_lines")

    op.drop_index("ix_issues_status", table_name="issues")
    op.drop_index("ix_issues_ngay_xuat", table_name="issues")
    op.drop_index("ix_issues_lot", table_name="issues")
    op.drop_index("ix_issues_nhu_cau", table_name="issues")
    op.drop_table("issues")

