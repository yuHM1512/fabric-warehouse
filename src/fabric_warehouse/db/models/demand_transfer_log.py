from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class DemandTransferLog(Base):
    __tablename__ = "demand_transfer_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    ma_cay: Mapped[str] = mapped_column(String(64), index=True)
    from_nhu_cau: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    from_lot: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    to_nhu_cau: Mapped[str] = mapped_column(String(64), index=True)
    to_lot: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_demand_transfer_logs_ma_cay_created_at", "ma_cay", "created_at"),
    )

