from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class PalletStockCheck(Base):
    __tablename__ = "pallet_stock_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("pallet_stock_check_sessions.id", ondelete="CASCADE"), index=True)

    vi_tri: Mapped[str] = mapped_column(String(16), index=True)
    ma_cay: Mapped[str] = mapped_column(String(64), index=True)
    nhu_cau: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lot: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    system_yards: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    expected_in_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    present_actual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_pallet_stock_checks_session_expected", "session_id", "expected_in_system"),
        Index("ix_pallet_stock_checks_vi_tri_expected", "vi_tri", "expected_in_system"),
    )
