"""make receipt_lines ma_cay unique

Revision ID: 20260424_012
Revises: 20260421_011
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op


revision = "20260424_012"
down_revision = "20260421_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM receipt_lines rl
        USING receipt_lines keep
        WHERE rl.ma_cay = keep.ma_cay
          AND rl.id > keep.id
        """
    )
    op.drop_index("ix_receipt_lines_ma_cay", table_name="receipt_lines")
    op.create_index("ix_receipt_lines_ma_cay", "receipt_lines", ["ma_cay"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_receipt_lines_ma_cay", table_name="receipt_lines")
    op.create_index("ix_receipt_lines_ma_cay", "receipt_lines", ["ma_cay"], unique=False)
