from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fabric_warehouse.db.base import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_filename: Mapped[str] = mapped_column(String(255))
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["ReceiptLine"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    roll_id: Mapped[int | None] = mapped_column(
        ForeignKey("fabric_rolls.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    ma_cay: Mapped[str] = mapped_column(String(64), index=True)
    nhu_cau: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    lot: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    anh_mau: Mapped[str] = mapped_column(String(64), default="CHUNG", index=True)

    model: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    art: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    yards: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    receipt: Mapped["Receipt"] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_receipt_lines_receipt_ma_cay", "receipt_id", "ma_cay", unique=True),
        Index("ix_receipt_lines_receipt_nhu_cau_lot", "receipt_id", "nhu_cau", "lot"),
        Index("ix_receipt_lines_roll_id_receipt_id", "roll_id", "receipt_id"),
        Index("ix_receipt_lines_raw_gin", "raw_data", postgresql_using="gin"),
    )
