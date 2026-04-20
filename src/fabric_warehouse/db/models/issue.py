from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fabric_warehouse.db.base import Base


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)

    nhu_cau: Mapped[str] = mapped_column(String(64), index=True)
    lot: Mapped[str] = mapped_column(String(64), index=True)
    ngay_xuat: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(64), default="Cấp phát sản xuất", index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["IssueLine"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class IssueLine(Base):
    __tablename__ = "issue_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)

    ma_cay: Mapped[str] = mapped_column(String(64), index=True)
    so_luong_xuat: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    vi_tri: Mapped[str | None] = mapped_column(String(16), nullable=True)

    issue: Mapped["Issue"] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_issue_lines_issue_ma_cay", "issue_id", "ma_cay", unique=True),
    )

