from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fabric_warehouse.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    ma_nv: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ho_ten: Mapped[str] = mapped_column(String(255), default="")
    chuc_vu: Mapped[str] = mapped_column(String(255), default="")
    don_vi: Mapped[str] = mapped_column(String(255), default="")
    bo_phan: Mapped[str] = mapped_column(String(255), default="")
    station: Mapped[list[str]] = mapped_column(JSONB, default=list)
