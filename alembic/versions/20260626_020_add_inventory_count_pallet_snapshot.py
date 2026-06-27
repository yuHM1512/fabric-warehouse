"""add pallet snapshot to inventory count rows

Revision ID: 20260626_020
Revises: 20260625_019
Create Date: 2026-06-26 09:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "20260626_020"
down_revision = "20260625_019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("inventory_count_rows")}
    if "pallet_snapshot" in column_names:
        return
    op.add_column(
        "inventory_count_rows",
        sa.Column(
            "pallet_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("inventory_count_rows")}
    if "pallet_snapshot" not in column_names:
        return
    op.drop_column("inventory_count_rows", "pallet_snapshot")
