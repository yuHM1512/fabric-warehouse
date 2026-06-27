from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class InventoryCountRow(Base):
    __tablename__ = "inventory_count_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_count_sessions.id", ondelete="CASCADE"),
        index=True,
    )

    ma_hang: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    loai_vai: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ten_vai: Mapped[str | None] = mapped_column(String(255), nullable=True)

    system_roll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    system_quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    pallet_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, server_default="[]")
    actual_quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_inventory_count_rows_session_group",
            "session_id",
            "ma_hang",
            "loai_vai",
            "ten_vai",
        ),
    )
