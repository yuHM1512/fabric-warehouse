from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class LocationAssignment(Base):
    __tablename__ = "location_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)

    ma_cay: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nhu_cau: Mapped[str] = mapped_column(String(64), index=True)
    lot: Mapped[str] = mapped_column(String(64), index=True)
    anh_mau: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    vi_tri: Mapped[str] = mapped_column(String(16), index=True)  # e.g. A.01.01
    trang_thai: Mapped[str] = mapped_column(String(32), default="Đang lưu", index=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_location_assignments_nhu_cau_lot", "nhu_cau", "lot"),
        Index("ix_location_assignments_vi_tri_trang_thai", "vi_tri", "trang_thai"),
    )

