from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class StockCheck(Base):
    __tablename__ = "stock_checks"

    id: Mapped[int] = mapped_column(primary_key=True)

    nhu_cau: Mapped[str] = mapped_column(String(64), index=True)
    lot: Mapped[str] = mapped_column(String(64), index=True)
    ma_cay: Mapped[str] = mapped_column(String(64), index=True)

    expected_yards: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    actual_yards: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ux_stock_checks_key", "nhu_cau", "lot", "ma_cay", unique=True),
        Index("ix_stock_checks_nhu_cau_lot", "nhu_cau", "lot"),
    )

