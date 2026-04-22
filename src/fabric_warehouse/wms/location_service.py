from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck


@dataclass(frozen=True)
class LocationRollRow:
    ma_cay: str
    expected_yards: float | None
    actual_yards: float | None
    vi_tri: str | None
    trang_thai: str | None


def tang_options() -> list[str]:
    return ["A", "B", "C"]


def line_options() -> list[str]:
    return [f"{i:02d}" for i in range(1, 5)]


def pallet_options() -> list[str]:
    # Legacy "Định danh vị trí" used 01-12 regardless of line.
    return [f"{i:02d}" for i in range(1, 13)]


def list_nhu_cau_options_for_location(db: Session) -> list[str]:
    rows = (
        db.query(StockCheck.nhu_cau)
        .filter(StockCheck.actual_yards.isnot(None))
        .distinct()
        .order_by(StockCheck.nhu_cau.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_anh_mau_options(db: Session, *, nhu_cau: str) -> list[str]:
    rows = (
        db.query(ReceiptLine.anh_mau)
        .join(StockCheck, (StockCheck.ma_cay == ReceiptLine.ma_cay) & StockCheck.actual_yards.isnot(None))
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.anh_mau.isnot(None))
        .distinct()
        .order_by(ReceiptLine.anh_mau.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_lot_options_for_location(db: Session, *, nhu_cau: str, anh_mau: str | None) -> list[str]:
    # Lots that have at least one checked roll and at least one roll not assigned yet.
    base = (
        db.query(ReceiptLine.lot)
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot.isnot(None))
    )
    if anh_mau:
        base = base.filter(ReceiptLine.anh_mau == anh_mau)

    lots = [r[0] for r in base.distinct().order_by(ReceiptLine.lot.asc()).all() if r[0]]
    if not lots:
        return []

    checked_lots = {
        r[0]
        for r in (
            db.query(StockCheck.lot)
            .filter(StockCheck.nhu_cau == nhu_cau)
            .filter(StockCheck.actual_yards.isnot(None))
            .filter(StockCheck.lot.in_(lots))
            .distinct()
            .all()
        )
        if r[0]
    }

    # Determine lots that are fully assigned among checked rolls: if every checked roll has a location.
    out: list[str] = []
    for lot in lots:
        if lot not in checked_lots:
            continue
        checked_rolls = (
            db.query(func.count(func.distinct(StockCheck.ma_cay)))
            .filter(StockCheck.nhu_cau == nhu_cau)
            .filter(StockCheck.lot == lot)
            .filter(StockCheck.actual_yards.isnot(None))
            .scalar()
        ) or 0
        if checked_rolls == 0:
            continue
        assigned_rolls = (
            db.query(func.count(func.distinct(LocationAssignment.ma_cay)))
            .filter(LocationAssignment.nhu_cau == nhu_cau)
            .filter(LocationAssignment.lot == lot)
            .filter(LocationAssignment.trang_thai == "Đang lưu")
            .scalar()
        ) or 0
        if assigned_rolls < checked_rolls:
            out.append(lot)

    return sorted(out)


def list_rolls_for_location(
    db: Session,
    *,
    nhu_cau: str,
    anh_mau: str | None,
    lot: str,
) -> list[LocationRollRow]:
    # rolls in receipts for that nhu_cau/lot/(anh_mau)
    q = (
        db.query(ReceiptLine.ma_cay, ReceiptLine.yards, ReceiptLine.anh_mau)
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot == lot)
    )
    if anh_mau:
        q = q.filter(ReceiptLine.anh_mau == anh_mau)

    receipt_rows = q.order_by(ReceiptLine.ma_cay.asc()).all()
    expected_by_ma_cay: dict[str, float | None] = {}
    for ma_cay, yards, _am in receipt_rows:
        if ma_cay and ma_cay not in expected_by_ma_cay:
            expected_by_ma_cay[ma_cay] = float(yards) if yards is not None else None

    checks = (
        db.query(StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.nhu_cau == nhu_cau)
        .filter(StockCheck.lot == lot)
        .filter(StockCheck.actual_yards.isnot(None))
        .all()
    )
    actual_by_ma_cay = {ma: float(ay) if ay is not None else None for ma, ay in checks}

    assigns = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.nhu_cau == nhu_cau)
        .filter(LocationAssignment.lot == lot)
        .filter(LocationAssignment.trang_thai == "Đang lưu")
        .all()
    )
    assign_by_ma_cay = {a.ma_cay: a for a in assigns}

    out: list[LocationRollRow] = []
    for ma_cay, expected in expected_by_ma_cay.items():
        actual = actual_by_ma_cay.get(ma_cay)
        a = assign_by_ma_cay.get(ma_cay)
        out.append(
            LocationRollRow(
                ma_cay=ma_cay,
                expected_yards=expected,
                actual_yards=actual,
                vi_tri=a.vi_tri if a else None,
                trang_thai=a.trang_thai if a else None,
            )
        )
    return out


def assign_location(
    db: Session,
    *,
    nhu_cau: str,
    lot: str,
    anh_mau: str | None,
    ma_cays: list[str],
    vi_tri: str,
) -> int:
    now = datetime.now(timezone.utc)

    cleaned: list[str] = []
    for ma in ma_cays:
        ma = (ma or "").strip()
        if ma:
            cleaned.append(ma)
    cleaned = list(dict.fromkeys(cleaned))
    if not cleaned:
        return 0

    existing_rows = (
        db.query(LocationAssignment.ma_cay, LocationAssignment.vi_tri, LocationAssignment.nhu_cau, LocationAssignment.lot)
        .filter(LocationAssignment.ma_cay.in_(cleaned))
        .all()
    )
    existing_map: dict[str, tuple[str | None, str | None, str | None]] = {
        str(ma): (
            (str(v) if v is not None else None),
            (str(nc) if nc is not None else None),
            (str(l) if l is not None else None),
        )
        for ma, v, nc, l in existing_rows
        if ma
    }

    values = []
    logs: list[LocationTransferLog] = []
    for ma in cleaned:
        values.append(
            {
                "ma_cay": ma,
                "nhu_cau": nhu_cau,
                "lot": lot,
                "anh_mau": anh_mau,
                "vi_tri": vi_tri,
                "trang_thai": "Đang lưu",
                "assigned_at": now,
                "updated_at": now,
            }
        )
        from_vi_tri, prev_nc, prev_lot = existing_map.get(ma, (None, None, None))
        if from_vi_tri == vi_tri:
            continue
        logs.append(
            LocationTransferLog(
                ma_cay=ma,
                nhu_cau=(prev_nc or nhu_cau),
                lot=(prev_lot or lot),
                from_vi_tri=from_vi_tri,
                to_vi_tri=vi_tri,
                note="assign_location",
                created_at=now,
            )
        )
    if not values:
        return 0

    if logs:
        db.add_all(logs)

    stmt = pg_insert(LocationAssignment.__table__).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ma_cay"],
        set_={
            "nhu_cau": stmt.excluded.nhu_cau,
            "lot": stmt.excluded.lot,
            "anh_mau": stmt.excluded.anh_mau,
            "vi_tri": stmt.excluded.vi_tri,
            "trang_thai": stmt.excluded.trang_thai,
            "assigned_at": func.coalesce(LocationAssignment.assigned_at, stmt.excluded.assigned_at),
            "updated_at": stmt.excluded.updated_at,
        },
    )
    res = db.execute(stmt)
    return int(res.rowcount or 0)
