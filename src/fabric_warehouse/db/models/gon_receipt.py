from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class GonReceipt(Base):
    __tablename__ = "gon_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)

    nha_cung_cap: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ten_gon: Mapped[str] = mapped_column(String(255))
    quy_cach: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ma_hang: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mua: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ngay_nhap: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_gon_receipts_supplier_item", "nha_cung_cap", "ma_hang"),
    )
