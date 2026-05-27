from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class GonTransfer(Base):
    __tablename__ = "gon_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    gon_type: Mapped[str] = mapped_column(String(255), index=True)
    so_kien: Mapped[float] = mapped_column(Numeric(12, 2))
    so_yds: Mapped[float] = mapped_column(Numeric(12, 2))
    from_vi_tri: Mapped[str] = mapped_column(String(16), index=True)
    to_vi_tri: Mapped[str] = mapped_column(String(16), index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_gon_transfers_type_from_to", "gon_type", "from_vi_tri", "to_vi_tri"),
    )
