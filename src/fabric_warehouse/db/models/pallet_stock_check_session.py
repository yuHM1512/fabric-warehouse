from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class PalletStockCheckSession(Base):
    __tablename__ = "pallet_stock_check_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    vi_tri: Mapped[str] = mapped_column(String(16), index=True)
    app_roll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_roll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_roll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
