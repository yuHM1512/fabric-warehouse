from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.gon_receipt import GonReceipt
from fabric_warehouse.db.models.gon_stock_entry import GonStockEntry
from fabric_warehouse.wms.location_service import expanded_block_options


def _as_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


@dataclass(frozen=True)
class GonBlockSummary:
    block: str
    entries: int
    total_kien: int
    total_yds: float


@dataclass(frozen=True)
class GonBlockRow:
    gon_type: str
    so_kien: int
    so_yds: float
    vi_tri: str
    created_at: object


def list_gon_type_options(db: Session) -> list[str]:
    rows = (
        db.query(GonReceipt.ten_gon)
        .filter(GonReceipt.ten_gon.isnot(None))
        .distinct()
        .order_by(GonReceipt.ten_gon.asc())
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]


def create_gon_stock_entry(
    db: Session,
    *,
    gon_type: str,
    so_kien: int,
    so_yds: float,
    warehouse_area: str,
    tang: str | None,
    line: str | None,
    pallet: str | None,
    block: str | None,
    vi_tri: str,
) -> GonStockEntry:
    item = GonStockEntry(
        gon_type=(gon_type or "").strip(),
        so_kien=int(so_kien),
        so_yds=float(so_yds),
        warehouse_area=(warehouse_area or "").strip(),
        tang=(tang or "").strip() or None,
        line=(line or "").strip() or None,
        pallet=(pallet or "").strip() or None,
        block=(block or "").strip() or None,
        vi_tri=(vi_tri or "").strip(),
    )
    db.add(item)
    db.flush()
    return item


def list_recent_gon_stock_entries(db: Session, *, limit: int = 30) -> list[GonStockEntry]:
    return db.query(GonStockEntry).order_by(GonStockEntry.created_at.desc(), GonStockEntry.id.desc()).limit(limit).all()


def get_expanded_block_summaries(db: Session) -> dict[str, GonBlockSummary]:
    rows = (
        db.query(
            GonStockEntry.block,
            func.count(GonStockEntry.id),
            func.coalesce(func.sum(GonStockEntry.so_kien), 0),
            func.coalesce(func.sum(GonStockEntry.so_yds), 0),
        )
        .filter(GonStockEntry.warehouse_area == "expanded")
        .filter(GonStockEntry.block.isnot(None))
        .group_by(GonStockEntry.block)
        .all()
    )
    by_block = {
        str(block): GonBlockSummary(
            block=str(block),
            entries=int(entries or 0),
            total_kien=int(total_kien or 0),
            total_yds=_as_float(total_yds, 0.0),
        )
        for block, entries, total_kien, total_yds in rows
        if block
    }
    return {
        block: by_block.get(
            block,
            GonBlockSummary(block=block, entries=0, total_kien=0, total_yds=0.0),
        )
        for block in expanded_block_options()
    }


def list_gon_block_rows(db: Session, *, block: str) -> list[GonBlockRow]:
    block_s = (block or "").strip()
    if block_s not in expanded_block_options():
        return []

    rows = (
        db.query(GonStockEntry)
        .filter(GonStockEntry.warehouse_area == "expanded")
        .filter(GonStockEntry.block == block_s)
        .order_by(GonStockEntry.created_at.desc(), GonStockEntry.id.desc())
        .all()
    )
    return [
        GonBlockRow(
            gon_type=str(row.gon_type or ""),
            so_kien=int(row.so_kien or 0),
            so_yds=_as_float(row.so_yds, 0.0),
            vi_tri=str(row.vi_tri or ""),
            created_at=row.created_at,
        )
        for row in rows
    ]


def get_gon_layout_totals(db: Session) -> dict[str, float]:
    row = (
        db.query(
            func.count(GonStockEntry.id),
            func.coalesce(func.sum(GonStockEntry.so_kien), 0),
            func.coalesce(func.sum(GonStockEntry.so_yds), 0),
        )
        .first()
    )
    if not row:
        return {"entries": 0, "total_kien": 0, "total_yds": 0.0}
    entries, total_kien, total_yds = row
    return {
        "entries": int(entries or 0),
        "total_kien": int(total_kien or 0),
        "total_yds": _as_float(total_yds, 0.0),
    }
