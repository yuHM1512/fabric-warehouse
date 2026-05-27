from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.gon_issue import GonIssue
from fabric_warehouse.db.models.gon_receipt import GonReceipt
from fabric_warehouse.db.models.gon_stock_entry import GonStockEntry
from fabric_warehouse.db.models.gon_transfer import GonTransfer
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


def _to_block(vi_tri: str | None) -> str | None:
    vi_tri_s = (vi_tri or "").strip()
    if vi_tri_s.startswith("MR."):
        return vi_tri_s[3:].strip() or None
    return None


@dataclass(frozen=True)
class GonBlockSummary:
    block: str
    entries: int
    total_kien: float
    total_yds: float


@dataclass(frozen=True)
class GonBlockRow:
    gon_type: str
    so_kien: float
    so_yds: float
    vi_tri: str


@dataclass(frozen=True)
class GonIssueCandidateRow:
    gon_type: str
    vi_tri: str
    so_kien: float
    so_yds: float


@dataclass(frozen=True)
class GonIssueHistoryRow:
    id: int
    gon_type: str
    from_vi_tri: str
    so_kien: float
    so_yds: float
    ngay_xuat: date
    note: str | None


@dataclass(frozen=True)
class GonTransferHistoryRow:
    id: int
    gon_type: str
    from_vi_tri: str
    to_vi_tri: str
    so_kien: float
    so_yds: float
    note: str | None
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


def _build_balance_map(db: Session) -> dict[tuple[str, str], tuple[float, float]]:
    balances: dict[tuple[str, str], tuple[float, float]] = {}

    def add(vi_tri: str | None, gon_type: str | None, so_kien: object, so_yds: object, sign: float) -> None:
        vi_tri_s = (vi_tri or "").strip()
        gon_type_s = (gon_type or "").strip()
        if not vi_tri_s or not gon_type_s:
            return
        key = (vi_tri_s, gon_type_s)
        current_kien, current_yds = balances.get(key, (0.0, 0.0))
        balances[key] = (
            current_kien + sign * _as_float(so_kien, 0.0),
            current_yds + sign * _as_float(so_yds, 0.0),
        )

    for row in db.query(GonStockEntry.vi_tri, GonStockEntry.gon_type, GonStockEntry.so_kien, GonStockEntry.so_yds).all():
        add(row[0], row[1], row[2], row[3], 1.0)
    for row in db.query(GonIssue.from_vi_tri, GonIssue.gon_type, GonIssue.so_kien, GonIssue.so_yds).all():
        add(row[0], row[1], row[2], row[3], -1.0)
    for row in db.query(GonTransfer.from_vi_tri, GonTransfer.to_vi_tri, GonTransfer.gon_type, GonTransfer.so_kien, GonTransfer.so_yds).all():
        add(row[0], row[2], row[3], row[4], -1.0)
        add(row[1], row[2], row[3], row[4], 1.0)
    return balances


def list_gon_issue_candidates(db: Session, *, gon_type: str | None = None, vi_tri: str | None = None) -> list[GonIssueCandidateRow]:
    gon_type_s = (gon_type or "").strip()
    vi_tri_s = (vi_tri or "").strip()
    rows: list[GonIssueCandidateRow] = []
    for (current_vi_tri, current_type), (so_kien, so_yds) in _build_balance_map(db).items():
        if so_kien <= 0 and so_yds <= 0:
            continue
        if gon_type_s and current_type != gon_type_s:
            continue
        if vi_tri_s and current_vi_tri != vi_tri_s:
            continue
        rows.append(
            GonIssueCandidateRow(
                gon_type=current_type,
                vi_tri=current_vi_tri,
                so_kien=round(so_kien, 2),
                so_yds=round(so_yds, 2),
            )
        )
    rows.sort(key=lambda item: (item.vi_tri, item.gon_type))
    return rows


def list_gon_issue_type_options(db: Session) -> list[str]:
    return sorted({row.gon_type for row in list_gon_issue_candidates(db) if row.gon_type})


def list_gon_issue_location_options(db: Session, *, gon_type: str) -> list[str]:
    return sorted({row.vi_tri for row in list_gon_issue_candidates(db, gon_type=gon_type) if row.vi_tri})


def create_gon_issue(
    db: Session,
    *,
    gon_type: str,
    from_vi_tri: str,
    so_kien: float,
    so_yds: float,
    ngay_xuat: date,
    note: str | None,
) -> GonIssue:
    balances = _build_balance_map(db)
    current_kien, current_yds = balances.get(((from_vi_tri or "").strip(), (gon_type or "").strip()), (0.0, 0.0))
    if so_kien > current_kien or so_yds > current_yds:
        raise ValueError("So luong gon xuat vuot ton hien tai.")

    issue = GonIssue(
        gon_type=(gon_type or "").strip(),
        from_vi_tri=(from_vi_tri or "").strip(),
        so_kien=float(so_kien),
        so_yds=float(so_yds),
        ngay_xuat=ngay_xuat,
        note=(note or "").strip() or None,
    )
    db.add(issue)
    db.flush()
    return issue


def list_gon_issue_history(
    db: Session,
    *,
    gon_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 1000,
) -> list[GonIssueHistoryRow]:
    q = db.query(GonIssue).order_by(GonIssue.ngay_xuat.desc(), GonIssue.id.desc())
    if gon_type:
        q = q.filter(GonIssue.gon_type == gon_type)
    if date_from:
        q = q.filter(GonIssue.ngay_xuat >= date_from)
    if date_to:
        q = q.filter(GonIssue.ngay_xuat <= date_to)
    return [
        GonIssueHistoryRow(
            id=row.id,
            gon_type=row.gon_type,
            from_vi_tri=row.from_vi_tri,
            so_kien=_as_float(row.so_kien, 0.0),
            so_yds=_as_float(row.so_yds, 0.0),
            ngay_xuat=row.ngay_xuat,
            note=row.note,
        )
        for row in q.limit(limit).all()
    ]


def create_gon_transfer(
    db: Session,
    *,
    gon_type: str,
    from_vi_tri: str,
    to_vi_tri: str,
    so_kien: float,
    so_yds: float,
    note: str | None,
) -> GonTransfer:
    from_vi_tri_s = (from_vi_tri or "").strip()
    to_vi_tri_s = (to_vi_tri or "").strip()
    gon_type_s = (gon_type or "").strip()
    if from_vi_tri_s == to_vi_tri_s:
        raise ValueError("Vi tri nhan phai khac vi tri xuat.")

    balances = _build_balance_map(db)
    current_kien, current_yds = balances.get((from_vi_tri_s, gon_type_s), (0.0, 0.0))
    if so_kien > current_kien or so_yds > current_yds:
        raise ValueError("So luong gon dieu chuyen vuot ton hien tai.")

    item = GonTransfer(
        gon_type=gon_type_s,
        from_vi_tri=from_vi_tri_s,
        to_vi_tri=to_vi_tri_s,
        so_kien=float(so_kien),
        so_yds=float(so_yds),
        note=(note or "").strip() or None,
    )
    db.add(item)
    db.flush()
    return item


def list_gon_transfer_history(db: Session, *, limit: int = 1000) -> list[GonTransferHistoryRow]:
    rows = db.query(GonTransfer).order_by(GonTransfer.created_at.desc(), GonTransfer.id.desc()).limit(limit).all()
    return [
        GonTransferHistoryRow(
            id=row.id,
            gon_type=row.gon_type,
            from_vi_tri=row.from_vi_tri,
            to_vi_tri=row.to_vi_tri,
            so_kien=_as_float(row.so_kien, 0.0),
            so_yds=_as_float(row.so_yds, 0.0),
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    ]


def get_expanded_block_summaries(db: Session) -> dict[str, GonBlockSummary]:
    summary_map: dict[str, GonBlockSummary] = {
        block: GonBlockSummary(block=block, entries=0, total_kien=0.0, total_yds=0.0)
        for block in expanded_block_options()
    }
    for (vi_tri, _gon_type), (so_kien, so_yds) in _build_balance_map(db).items():
        block = _to_block(vi_tri)
        if not block or block not in summary_map:
            continue
        current = summary_map[block]
        summary_map[block] = GonBlockSummary(
            block=block,
            entries=current.entries + 1,
            total_kien=round(current.total_kien + max(0.0, so_kien), 2),
            total_yds=round(current.total_yds + max(0.0, so_yds), 2),
        )
    return summary_map


def list_gon_block_rows(db: Session, *, block: str) -> list[GonBlockRow]:
    block_s = (block or "").strip()
    if block_s not in expanded_block_options():
        return []
    vi_tri = f"MR.{block_s}"
    rows: list[GonBlockRow] = []
    for (current_vi_tri, gon_type), (so_kien, so_yds) in _build_balance_map(db).items():
        if current_vi_tri != vi_tri:
            continue
        if so_kien <= 0 and so_yds <= 0:
            continue
        rows.append(
            GonBlockRow(
                gon_type=gon_type,
                so_kien=round(so_kien, 2),
                so_yds=round(so_yds, 2),
                vi_tri=current_vi_tri,
            )
        )
    rows.sort(key=lambda row: row.gon_type)
    return rows


def get_gon_layout_totals(db: Session) -> dict[str, float]:
    total_entries = 0
    total_kien = 0.0
    total_yds = 0.0
    for (vi_tri, _gon_type), (so_kien, so_yds) in _build_balance_map(db).items():
        if not _to_block(vi_tri):
            continue
        if so_kien <= 0 and so_yds <= 0:
            continue
        total_entries += 1
        total_kien += max(0.0, so_kien)
        total_yds += max(0.0, so_yds)
    return {
        "entries": total_entries,
        "total_kien": round(total_kien, 2),
        "total_yds": round(total_yds, 2),
    }
