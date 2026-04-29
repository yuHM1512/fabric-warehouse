from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck


@dataclass(frozen=True)
class StockCheckRow:
    ma_cay: str
    expected_yards: float | None
    actual_yards: float | None
    note: str | None
    updated_at: datetime | None


def list_nhu_cau_options(db: Session) -> list[str]:
    """
    UX: only show demands that are not fully stock-checked yet.

    A demand is considered completed when every distinct `ma_cay` in receipts has a
    stock_check row with `actual_yards` filled.
    """
    receipt_sq = (
        db.query(
            ReceiptLine.nhu_cau.label("nhu_cau"),
            ReceiptLine.ma_cay.label("ma_cay"),
        )
        .filter(ReceiptLine.nhu_cau.isnot(None))
        .filter(ReceiptLine.ma_cay.isnot(None))
        .distinct()
        .subquery()
    )

    total_sq = (
        db.query(
            receipt_sq.c.nhu_cau.label("nhu_cau"),
            func.count(receipt_sq.c.ma_cay).label("total"),
        )
        .group_by(receipt_sq.c.nhu_cau)
        .subquery()
    )

    checked_sq = (
        db.query(
            receipt_sq.c.nhu_cau.label("nhu_cau"),
            func.count(func.distinct(StockCheck.ma_cay)).label("checked"),
        )
        .join(
            StockCheck,
            (StockCheck.nhu_cau == receipt_sq.c.nhu_cau) & (StockCheck.ma_cay == receipt_sq.c.ma_cay),
        )
        .filter(StockCheck.actual_yards.isnot(None))
        .group_by(receipt_sq.c.nhu_cau)
        .subquery()
    )

    rows = (
        db.query(total_sq.c.nhu_cau)
        .outerjoin(checked_sq, checked_sq.c.nhu_cau == total_sq.c.nhu_cau)
        .filter((checked_sq.c.checked.is_(None)) | (checked_sq.c.checked < total_sq.c.total))
        .order_by(total_sq.c.nhu_cau.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_lot_options(db: Session, *, nhu_cau: str) -> list[str]:
    """
    Return lots that are NOT fully checked yet (UX: hide completed lots).

    A lot is considered completed when every distinct `ma_cay` in receipts has a
    stock_check row with `actual_yards` filled.
    """
    receipt_sq = (
        db.query(
            ReceiptLine.lot.label("lot"),
            ReceiptLine.ma_cay.label("ma_cay"),
        )
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot.isnot(None))
        .filter(ReceiptLine.ma_cay.isnot(None))
        .distinct()
        .subquery()
    )

    total_sq = (
        db.query(
            receipt_sq.c.lot.label("lot"),
            func.count(receipt_sq.c.ma_cay).label("total"),
        )
        .group_by(receipt_sq.c.lot)
        .subquery()
    )

    checked_sq = (
        db.query(
            receipt_sq.c.lot.label("lot"),
            func.count(func.distinct(StockCheck.ma_cay)).label("checked"),
        )
        .join(
            StockCheck,
            (StockCheck.nhu_cau == nhu_cau)
            & (StockCheck.lot == receipt_sq.c.lot)
            & (StockCheck.ma_cay == receipt_sq.c.ma_cay),
        )
        .filter(StockCheck.actual_yards.isnot(None))
        .group_by(receipt_sq.c.lot)
        .subquery()
    )

    rows = (
        db.query(total_sq.c.lot)
        .outerjoin(checked_sq, checked_sq.c.lot == total_sq.c.lot)
        .filter((checked_sq.c.checked.is_(None)) | (checked_sq.c.checked < total_sq.c.total))
        .order_by(total_sq.c.lot.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


@dataclass(frozen=True)
class LotSummaryRow:
    lot: str
    so_cay: int
    tong_yds: float


def list_incomplete_lot_summaries(db: Session, *, nhu_cau: str) -> list[LotSummaryRow]:
    """
    Summary table for the selected demand:
    Lot | Số cây | Số YDS

    Only includes lots that are not fully checked yet (same rule as list_lot_options).
    """
    receipt_sq = (
        db.query(
            ReceiptLine.lot.label("lot"),
            ReceiptLine.ma_cay.label("ma_cay"),
        )
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot.isnot(None))
        .filter(ReceiptLine.ma_cay.isnot(None))
        .distinct()
        .subquery()
    )

    total_sq = (
        db.query(
            ReceiptLine.lot.label("lot"),
            func.count(func.distinct(ReceiptLine.ma_cay)).label("total"),
            func.coalesce(func.sum(ReceiptLine.yards), 0).label("sum_yds"),
        )
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot.isnot(None))
        .group_by(ReceiptLine.lot)
        .subquery()
    )

    checked_sq = (
        db.query(
            receipt_sq.c.lot.label("lot"),
            func.count(func.distinct(StockCheck.ma_cay)).label("checked"),
        )
        .join(
            StockCheck,
            (StockCheck.nhu_cau == nhu_cau)
            & (StockCheck.lot == receipt_sq.c.lot)
            & (StockCheck.ma_cay == receipt_sq.c.ma_cay),
        )
        .filter(StockCheck.actual_yards.isnot(None))
        .group_by(receipt_sq.c.lot)
        .subquery()
    )

    rows = (
        db.query(total_sq.c.lot, total_sq.c.total, total_sq.c.sum_yds)
        .outerjoin(checked_sq, checked_sq.c.lot == total_sq.c.lot)
        .filter((checked_sq.c.checked.is_(None)) | (checked_sq.c.checked < total_sq.c.total))
        .order_by(total_sq.c.lot.asc())
        .all()
    )

    out: list[LotSummaryRow] = []
    for lot, total, sum_yds in rows:
        if not lot:
            continue
        out.append(LotSummaryRow(lot=str(lot), so_cay=int(total or 0), tong_yds=float(sum_yds or 0)))
    return out


def get_roll_rows(db: Session, *, nhu_cau: str, lot: str) -> list[StockCheckRow]:
    # base from receipts
    receipt_rows = (
        db.query(ReceiptLine.ma_cay, ReceiptLine.yards)
        .filter(ReceiptLine.nhu_cau == nhu_cau)
        .filter(ReceiptLine.lot == lot)
        .order_by(ReceiptLine.ma_cay.asc())
        .all()
    )
    expected_by_ma_cay: dict[str, float | None] = {}
    for ma_cay, yards in receipt_rows:
        if ma_cay and ma_cay not in expected_by_ma_cay:
            expected_by_ma_cay[ma_cay] = float(yards) if yards is not None else None

    checks = (
        db.query(StockCheck)
        .filter(StockCheck.nhu_cau == nhu_cau)
        .filter(StockCheck.lot == lot)
        .all()
    )
    check_by_ma_cay = {c.ma_cay: c for c in checks}

    out: list[StockCheckRow] = []
    for ma_cay, expected in expected_by_ma_cay.items():
        c = check_by_ma_cay.get(ma_cay)
        out.append(
            StockCheckRow(
                ma_cay=ma_cay,
                expected_yards=expected,
                actual_yards=float(c.actual_yards) if (c and c.actual_yards is not None) else None,
                note=c.note if c else None,
                updated_at=c.updated_at if c else None,
            )
        )
    return out


def upsert_stock_checks(
    db: Session,
    *,
    nhu_cau: str,
    lot: str,
    items: list[dict],
) -> int:
    """
    items: [{ma_cay, expected_yards, actual_yards, note}]
    Upsert by (nhu_cau, lot, ma_cay).
    """
    now = datetime.now(timezone.utc)
    values = []
    for it in items:
        ma_cay = (it.get("ma_cay") or "").strip()
        if not ma_cay:
            continue
        values.append(
            {
                "nhu_cau": nhu_cau,
                "lot": lot,
                "ma_cay": ma_cay,
                "expected_yards": it.get("expected_yards"),
                "actual_yards": it.get("actual_yards"),
                "note": (it.get("note") or "").strip() or None,
                "updated_at": now,
            }
        )

    if not values:
        return 0

    stmt = pg_insert(StockCheck.__table__).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["nhu_cau", "lot", "ma_cay"],
        set_={
            "expected_yards": stmt.excluded.expected_yards,
            "actual_yards": stmt.excluded.actual_yards,
            "note": stmt.excluded.note,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    res = db.execute(stmt)
    return int(res.rowcount or 0)
