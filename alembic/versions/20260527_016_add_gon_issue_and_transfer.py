"""add gon issue and transfer

Revision ID: 20260527_016
Revises: 20260527_015
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_016"
down_revision = "20260527_015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gon_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gon_type", sa.String(length=255), nullable=False),
        sa.Column("so_kien", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("so_yds", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("from_vi_tri", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("ngay_xuat", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gon_issues_gon_type", "gon_issues", ["gon_type"], unique=False)
    op.create_index("ix_gon_issues_from_vi_tri", "gon_issues", ["from_vi_tri"], unique=False)
    op.create_index("ix_gon_issues_ngay_xuat", "gon_issues", ["ngay_xuat"], unique=False)
    op.create_index("ix_gon_issues_created_at", "gon_issues", ["created_at"], unique=False)
    op.create_index("ix_gon_issues_type_vi_tri", "gon_issues", ["gon_type", "from_vi_tri"], unique=False)

    op.create_table(
        "gon_transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gon_type", sa.String(length=255), nullable=False),
        sa.Column("so_kien", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("so_yds", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("from_vi_tri", sa.String(length=16), nullable=False),
        sa.Column("to_vi_tri", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gon_transfers_gon_type", "gon_transfers", ["gon_type"], unique=False)
    op.create_index("ix_gon_transfers_from_vi_tri", "gon_transfers", ["from_vi_tri"], unique=False)
    op.create_index("ix_gon_transfers_to_vi_tri", "gon_transfers", ["to_vi_tri"], unique=False)
    op.create_index("ix_gon_transfers_created_at", "gon_transfers", ["created_at"], unique=False)
    op.create_index("ix_gon_transfers_type_from_to", "gon_transfers", ["gon_type", "from_vi_tri", "to_vi_tri"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gon_transfers_type_from_to", table_name="gon_transfers")
    op.drop_index("ix_gon_transfers_created_at", table_name="gon_transfers")
    op.drop_index("ix_gon_transfers_to_vi_tri", table_name="gon_transfers")
    op.drop_index("ix_gon_transfers_from_vi_tri", table_name="gon_transfers")
    op.drop_index("ix_gon_transfers_gon_type", table_name="gon_transfers")
    op.drop_table("gon_transfers")

    op.drop_index("ix_gon_issues_type_vi_tri", table_name="gon_issues")
    op.drop_index("ix_gon_issues_created_at", table_name="gon_issues")
    op.drop_index("ix_gon_issues_ngay_xuat", table_name="gon_issues")
    op.drop_index("ix_gon_issues_from_vi_tri", table_name="gon_issues")
    op.drop_index("ix_gon_issues_gon_type", table_name="gon_issues")
    op.drop_table("gon_issues")
