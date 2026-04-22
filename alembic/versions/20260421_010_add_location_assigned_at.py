"""add location_assignments.assigned_at

Revision ID: 20260421_010
Revises: 20260420_009
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_010"
down_revision = "20260420_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "location_assignments",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_location_assignments_assigned_at",
        "location_assignments",
        ["assigned_at"],
        unique=False,
    )

    # Backfill: prefer first "from_vi_tri is NULL" transfer log (first assignment),
    # fallback to updated_at, then now().
    op.execute(
        sa.text(
            """
            UPDATE location_assignments la
            SET assigned_at = COALESCE(
              (
                SELECT MIN(ltl.created_at)
                FROM location_transfer_logs ltl
                WHERE ltl.ma_cay = la.ma_cay
                  AND ltl.from_vi_tri IS NULL
              ),
              la.updated_at,
              now()
            )
            WHERE la.assigned_at IS NULL
            """
        )
    )

    op.alter_column(
        "location_assignments",
        "assigned_at",
        nullable=False,
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
    )


def downgrade() -> None:
    op.drop_index("ix_location_assignments_assigned_at", table_name="location_assignments")
    op.drop_column("location_assignments", "assigned_at")

