from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class FabricData(Base):
    __tablename__ = "fabric_data"

    id: Mapped[int] = mapped_column(primary_key=True)

    ma_model: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ten_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    yrd_per_pallet: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True, index=True)
    usd_per_yrd: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (
        Index("ix_fabric_data_raw_gin", "raw_data", postgresql_using="gin"),
    )

