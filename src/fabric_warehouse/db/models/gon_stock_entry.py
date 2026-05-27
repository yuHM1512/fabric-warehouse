from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class GonStockEntry(Base):
    __tablename__ = "gon_stock_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    gon_type: Mapped[str] = mapped_column(String(255), index=True)
    so_kien: Mapped[int] = mapped_column(Integer)
    so_yds: Mapped[float] = mapped_column(Numeric(12, 2))

    warehouse_area: Mapped[str] = mapped_column(String(16), index=True)  # main | expanded
    tang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    line: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pallet: Mapped[str | None] = mapped_column(String(8), nullable=True)
    block: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    vi_tri: Mapped[str] = mapped_column(String(16), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_gon_stock_entries_area_vi_tri", "warehouse_area", "vi_tri"),
        Index("ix_gon_stock_entries_block_created_at", "block", "created_at"),
    )
