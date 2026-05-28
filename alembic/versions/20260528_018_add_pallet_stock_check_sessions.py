"""add pallet stock check sessions

Revision ID: 20260528_018
Revises: 20260528_017
Create Date: 2026-05-28 12:20:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260528_018"
down_revision = "20260528_017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pallet_stock_check_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vi_tri", sa.String(length=16), nullable=False),
        sa.Column("app_roll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_roll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_roll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pallet_stock_check_sessions_created_at", "pallet_stock_check_sessions", ["created_at"], unique=False)
    op.create_index("ix_pallet_stock_check_sessions_vi_tri", "pallet_stock_check_sessions", ["vi_tri"], unique=False)

    op.add_column("pallet_stock_checks", sa.Column("session_id", sa.Integer(), nullable=True))
    op.create_index("ix_pallet_stock_checks_session_id", "pallet_stock_checks", ["session_id"], unique=False)
    op.create_index(
        "ix_pallet_stock_checks_session_expected",
        "pallet_stock_checks",
        ["session_id", "expected_in_system"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_pallet_stock_checks_session_id",
        "pallet_stock_checks",
        "pallet_stock_check_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ux_pallet_stock_checks_vi_tri_ma_cay", table_name="pallet_stock_checks")

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO pallet_stock_check_sessions (
                vi_tri,
                app_roll_count,
                matched_roll_count,
                extra_roll_count,
                created_at
            )
            SELECT
                pcs.vi_tri,
                COUNT(*) FILTER (WHERE pcs.expected_in_system IS TRUE) AS app_roll_count,
                COUNT(*) FILTER (
                    WHERE pcs.expected_in_system IS TRUE
                    AND pcs.present_actual IS TRUE
                ) AS matched_roll_count,
                COUNT(*) FILTER (WHERE pcs.expected_in_system IS FALSE) AS extra_roll_count,
                COALESCE(MAX(pcs.updated_at), MAX(pcs.created_at), NOW()) AS created_at
            FROM pallet_stock_checks pcs
            WHERE pcs.session_id IS NULL
            GROUP BY pcs.vi_tri
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE pallet_stock_checks pcs
            SET session_id = sess.id
            FROM pallet_stock_check_sessions sess
            WHERE pcs.session_id IS NULL
              AND sess.vi_tri = pcs.vi_tri
              AND sess.created_at = (
                  SELECT COALESCE(MAX(pcs2.updated_at), MAX(pcs2.created_at), sess.created_at)
                  FROM pallet_stock_checks pcs2
                  WHERE pcs2.vi_tri = pcs.vi_tri
              )
            """
        )
    )

    op.alter_column("pallet_stock_checks", "session_id", nullable=False)


def downgrade() -> None:
    op.create_index(
        "ux_pallet_stock_checks_vi_tri_ma_cay",
        "pallet_stock_checks",
        ["vi_tri", "ma_cay"],
        unique=True,
    )
    op.drop_constraint("fk_pallet_stock_checks_session_id", "pallet_stock_checks", type_="foreignkey")
    op.drop_index("ix_pallet_stock_checks_session_expected", table_name="pallet_stock_checks")
    op.drop_index("ix_pallet_stock_checks_session_id", table_name="pallet_stock_checks")
    op.drop_column("pallet_stock_checks", "session_id")

    op.drop_index("ix_pallet_stock_check_sessions_vi_tri", table_name="pallet_stock_check_sessions")
    op.drop_index("ix_pallet_stock_check_sessions_created_at", table_name="pallet_stock_check_sessions")
    op.drop_table("pallet_stock_check_sessions")
