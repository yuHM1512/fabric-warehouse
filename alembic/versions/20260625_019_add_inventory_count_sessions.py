"""add inventory count sessions

Revision ID: 20260625_019
Revises: 20260528_018
Create Date: 2026-06-25 22:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260625_019"
down_revision = "20260528_018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_count_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_count_sessions_created_at", "inventory_count_sessions", ["created_at"], unique=False)
    op.create_index("ix_inventory_count_sessions_session_date", "inventory_count_sessions", ["session_date"], unique=False)
    op.create_index("ix_inventory_count_sessions_status", "inventory_count_sessions", ["status"], unique=False)

    op.create_table(
        "inventory_count_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("ma_hang", sa.String(length=32), nullable=True),
        sa.Column("loai_vai", sa.String(length=500), nullable=True),
        sa.Column("ten_vai", sa.String(length=255), nullable=True),
        sa.Column("system_roll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("system_quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("pallet_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actual_quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["inventory_count_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_count_rows_ma_hang", "inventory_count_rows", ["ma_hang"], unique=False)
    op.create_index("ix_inventory_count_rows_session_id", "inventory_count_rows", ["session_id"], unique=False)
    op.create_index("ix_inventory_count_rows_updated_at", "inventory_count_rows", ["updated_at"], unique=False)
    op.create_index(
        "ix_inventory_count_rows_session_group",
        "inventory_count_rows",
        ["session_id", "ma_hang", "loai_vai", "ten_vai"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_count_rows_session_group", table_name="inventory_count_rows")
    op.drop_index("ix_inventory_count_rows_updated_at", table_name="inventory_count_rows")
    op.drop_index("ix_inventory_count_rows_session_id", table_name="inventory_count_rows")
    op.drop_index("ix_inventory_count_rows_ma_hang", table_name="inventory_count_rows")
    op.drop_table("inventory_count_rows")

    op.drop_index("ix_inventory_count_sessions_status", table_name="inventory_count_sessions")
    op.drop_index("ix_inventory_count_sessions_session_date", table_name="inventory_count_sessions")
    op.drop_index("ix_inventory_count_sessions_created_at", table_name="inventory_count_sessions")
    op.drop_table("inventory_count_sessions")
