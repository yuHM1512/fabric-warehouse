"""add pallet stock checks

Revision ID: 20260528_017
Revises: 20260527_016
Create Date: 2026-05-28 11:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260528_017"
down_revision = "20260527_016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pallet_stock_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vi_tri", sa.String(length=16), nullable=False),
        sa.Column("ma_cay", sa.String(length=64), nullable=False),
        sa.Column("nhu_cau", sa.String(length=64), nullable=True),
        sa.Column("lot", sa.String(length=64), nullable=True),
        sa.Column("system_yards", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("expected_in_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("present_actual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pallet_stock_checks_lot", "pallet_stock_checks", ["lot"], unique=False)
    op.create_index("ix_pallet_stock_checks_ma_cay", "pallet_stock_checks", ["ma_cay"], unique=False)
    op.create_index("ix_pallet_stock_checks_nhu_cau", "pallet_stock_checks", ["nhu_cau"], unique=False)
    op.create_index("ix_pallet_stock_checks_vi_tri", "pallet_stock_checks", ["vi_tri"], unique=False)
    op.create_index(
        "ix_pallet_stock_checks_vi_tri_expected",
        "pallet_stock_checks",
        ["vi_tri", "expected_in_system"],
        unique=False,
    )
    op.create_index(
        "ux_pallet_stock_checks_vi_tri_ma_cay",
        "pallet_stock_checks",
        ["vi_tri", "ma_cay"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_pallet_stock_checks_vi_tri_ma_cay", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_vi_tri_expected", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_vi_tri", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_nhu_cau", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_ma_cay", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_lot", table_name="pallet_stock_checks")
    op.drop_table("pallet_stock_checks")
