"""add users table (ma_nv)

Revision ID: 20260421_011
Revises: 20260421_010
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421_011"
down_revision = "20260421_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ma_nv", sa.String(length=32), nullable=False),
        sa.Column("ho_ten", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("chuc_vu", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("don_vi", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("bo_phan", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "station",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_users_ma_nv", "users", ["ma_nv"], unique=True)
    op.create_index("ix_users_don_vi", "users", ["don_vi"], unique=False)
    op.create_index("ix_users_bo_phan", "users", ["bo_phan"], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO users (ma_nv, ho_ten, chuc_vu, don_vi, bo_phan, station)
            VALUES
              ('ADMIN', 'admin', 'admin', 'P.TH', 'KSHT', '[]'::jsonb),
              ('H9253', 'Nguyễn Thị Thu Hà', 'Nhân viên kho', 'XNDT', 'Kho nguyên liệu', '[]'::jsonb)
            ON CONFLICT (ma_nv) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_users_bo_phan", table_name="users")
    op.drop_index("ix_users_don_vi", table_name="users")
    op.drop_index("ix_users_ma_nv", table_name="users")
    op.drop_table("users")

