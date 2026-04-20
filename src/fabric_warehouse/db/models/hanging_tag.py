from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class HangingTag(Base):
    __tablename__ = "hanging_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)

    id_bang_treo: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    ngay_nhap_hang: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    nhu_cau: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lot: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ma_hang: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    nha_cung_cap: Mapped[str | None] = mapped_column(String(255), nullable=True)
    khach_hang: Mapped[str | None] = mapped_column(String(255), nullable=True)

    loai_vai: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ma_art: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mau_vai: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ma_mau: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ngay_xuat: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    ket_qua_kiem_tra: Mapped[str | None] = mapped_column(String(64), nullable=True, default="OK")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_hanging_tags_receipt_nhu_cau_lot", "receipt_id", "nhu_cau", "lot"),
    )
