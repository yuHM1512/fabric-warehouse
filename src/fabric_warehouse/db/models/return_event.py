from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fabric_warehouse.db.base import Base


class ReturnEvent(Base):
    __tablename__ = "return_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_line_id: Mapped[int] = mapped_column(ForeignKey("issue_lines.id", ondelete="CASCADE"), index=True, unique=True)

    ma_cay: Mapped[str] = mapped_column(String(64), index=True)
    ngay_tai_nhap: Mapped[date] = mapped_column(Date, index=True)

    yds_du: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(64), index=True)  # "Tái nhập kho" / "Trả Mẹ Nhu" / ...

    nhu_cau_moi: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lot_moi: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vi_tri_moi: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue_line: Mapped["IssueLine"] = relationship()  # type: ignore[name-defined]

    __table_args__ = (
        Index("ix_return_events_issue_line_id", "issue_line_id", unique=True),
        Index("ix_return_events_ma_cay", "ma_cay"),
    )

