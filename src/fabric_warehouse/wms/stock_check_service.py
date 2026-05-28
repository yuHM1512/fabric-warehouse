from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.pallet_stock_check import PalletStockCheck
from fabric_warehouse.db.models.pallet_stock_check_session import PalletStockCheckSession
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent
from fabric_warehouse.db.models.stock_check import StockCheck


@dataclass(frozen=True)
class StockCheckRow:
    ma_cay: str
    expected_yards: float | None
    actual_yards: float | None
    note: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PalletAuditRow:
    ma_cay: str
    nhu_cau: str | None
    lot: str | None
    system_yards: float | None
    present_actual: bool
    expected_in_system: bool
    vi_tri_he_thong: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PalletAuditSuggestion:
    ma_cay: str
    nhu_cau: str | None
    lot: str | None
    system_yards: float | None
    vi_tri: str | None


@dataclass(frozen=True)
class PalletAuditSessionSummary:
    session_id: int
    created_at: datetime | None
    vi_tri: str
    app_roll_count: int
    matched_roll_count: int
    extra_roll_count: int


@dataclass(frozen=True)
class PalletAuditSessionDetail:
    session_id: int
    created_at: datetime | None
    vi_tri: str
    app_roll_count: int
    matched_roll_count: int
    extra_roll_count: int
    rows: list[PalletAuditRow]


def _latest_return_created_at_map(
    db: Session,
    *,
    ma_cays: list[str],
) -> dict[str, datetime]:
    if not ma_cays:
        return {}

    rows = (
        db.query(ReturnEvent.ma_cay, ReturnEvent.created_at)
        .filter(ReturnEvent.ma_cay.in_(ma_cays))
        .filter(ReturnEvent.created_at.isnot(None))
        .order_by(ReturnEvent.ma_cay.asc(), ReturnEvent.created_at.desc(), ReturnEvent.id.desc())
        .all()
    )
    out: dict[str, datetime] = {}
    for ma_cay, created_at in rows:
        ma = str(ma_cay or "").strip()
        if not ma or ma in out or created_at is None:
            continue
        out[ma] = created_at
    return out


def _latest_return_yards_map(
    db: Session,
    *,
    ma_cays: list[str],
) -> dict[str, float | None]:
    if not ma_cays:
        return {}

    rows = (
        db.query(ReturnEvent.ma_cay, ReturnEvent.yds_du, ReturnEvent.created_at)
        .filter(ReturnEvent.ma_cay.in_(ma_cays))
        .filter(ReturnEvent.vi_tri_moi.isnot(None))
        .order_by(ReturnEvent.ma_cay.asc(), ReturnEvent.created_at.desc(), ReturnEvent.id.desc())
        .all()
    )
    out: dict[str, float | None] = {}
    for ma_cay, yds_du, _created_at in rows:
        ma = str(ma_cay or "").strip()
        if not ma or ma in out:
            continue
        out[ma] = _to_float(yds_du)
    return out


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _effective_system_yards_map(
    db: Session,
    *,
    ma_cays: list[str],
) -> dict[str, float | None]:
    cleaned = [str(ma or "").strip() for ma in ma_cays if str(ma or "").strip()]
    cleaned = list(dict.fromkeys(cleaned))
    if not cleaned:
        return {}

    receipt_rows = (
        db.query(ReceiptLine.ma_cay, ReceiptLine.yards)
        .filter(ReceiptLine.ma_cay.in_(cleaned))
        .all()
    )
    out: dict[str, float | None] = {}
    for ma_cay, yards in receipt_rows:
        ma = str(ma_cay or "").strip()
        if not ma or ma in out:
            continue
        out[ma] = _to_float(yards)

    return_yards_map = _latest_return_yards_map(db, ma_cays=cleaned)
    for ma_cay, yds_du in return_yards_map.items():
        if yds_du is not None:
            out[ma_cay] = yds_du
    return out


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
    return_created_at_by_ma_cay = _latest_return_created_at_map(db, ma_cays=list(expected_by_ma_cay.keys()))

    out: list[StockCheckRow] = []
    for ma_cay, expected in expected_by_ma_cay.items():
        c = check_by_ma_cay.get(ma_cay)
        updated_at = c.updated_at if c else None
        returned_at = return_created_at_by_ma_cay.get(ma_cay)
        if returned_at and (updated_at is None or returned_at > updated_at):
            updated_at = returned_at
        out.append(
            StockCheckRow(
                ma_cay=ma_cay,
                expected_yards=expected,
                actual_yards=float(c.actual_yards) if (c and c.actual_yards is not None) else None,
                note=c.note if c else None,
                updated_at=updated_at,
            )
        )
    return out


def get_pallet_audit_rows(db: Session, *, vi_tri: str) -> list[PalletAuditRow]:
    vi_tri_s = (vi_tri or "").strip()
    if not vi_tri_s:
        return []

    existing_rows = (
        db.query(
            LocationAssignment.ma_cay,
            LocationAssignment.nhu_cau,
            LocationAssignment.lot,
            LocationAssignment.vi_tri,
        )
        .filter(LocationAssignment.vi_tri == vi_tri_s)
        .filter(LocationAssignment.trang_thai.in_(("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")))
        .order_by(LocationAssignment.ma_cay.asc())
        .all()
    )
    system_yards_map = _effective_system_yards_map(
        db,
        ma_cays=[str(ma_cay) for ma_cay, _nhu_cau, _lot, _vi_tri in existing_rows if ma_cay],
    )

    rows: list[PalletAuditRow] = []
    for ma_cay, nhu_cau, lot, current_vi_tri in existing_rows:
        ma = str(ma_cay or "").strip()
        if not ma:
            continue
        rows.append(
            PalletAuditRow(
                ma_cay=ma,
                nhu_cau=str(nhu_cau) if nhu_cau else None,
                lot=str(lot) if lot else None,
                system_yards=system_yards_map.get(ma),
                present_actual=False,
                expected_in_system=True,
                vi_tri_he_thong=str(current_vi_tri) if current_vi_tri else None,
                updated_at=None,
            )
        )

    rows.sort(key=lambda row: row.ma_cay)
    return rows


def search_pallet_audit_rolls(
    db: Session,
    *,
    q: str,
    vi_tri: str,
    limit: int = 12,
) -> list[PalletAuditSuggestion]:
    q_s = (q or "").strip()
    vi_tri_s = (vi_tri or "").strip()
    if len(q_s) < 2:
        return []

    rows = (
        db.query(
            LocationAssignment.ma_cay,
            LocationAssignment.nhu_cau,
            LocationAssignment.lot,
            LocationAssignment.vi_tri,
        )
        .filter(LocationAssignment.trang_thai.in_(("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")))
        .filter(LocationAssignment.vi_tri != vi_tri_s)
        .filter(LocationAssignment.ma_cay.ilike(f"%{q_s}%"))
        .order_by(LocationAssignment.ma_cay.asc())
        .limit(limit)
        .all()
    )
    system_yards_map = _effective_system_yards_map(
        db,
        ma_cays=[str(ma_cay) for ma_cay, _nhu_cau, _lot, _vi_tri in rows if ma_cay],
    )
    return [
        PalletAuditSuggestion(
            ma_cay=str(ma_cay),
            nhu_cau=str(nhu_cau) if nhu_cau else None,
            lot=str(lot) if lot else None,
            system_yards=system_yards_map.get(str(ma_cay)),
            vi_tri=str(current_vi_tri) if current_vi_tri else None,
        )
        for ma_cay, nhu_cau, lot, current_vi_tri in rows
        if ma_cay
    ]


def list_pallet_audit_sessions(db: Session, *, limit: int = 100) -> list[PalletAuditSessionSummary]:
    rows = (
        db.query(PalletStockCheckSession)
        .order_by(PalletStockCheckSession.created_at.desc(), PalletStockCheckSession.id.desc())
        .limit(limit)
        .all()
    )
    return [
        PalletAuditSessionSummary(
            session_id=row.id,
            created_at=row.created_at,
            vi_tri=row.vi_tri,
            app_roll_count=int(row.app_roll_count or 0),
            matched_roll_count=int(row.matched_roll_count or 0),
            extra_roll_count=int(row.extra_roll_count or 0),
        )
        for row in rows
    ]


def get_pallet_audit_session_detail(db: Session, *, session_id: int) -> PalletAuditSessionDetail | None:
    session_row = db.query(PalletStockCheckSession).filter(PalletStockCheckSession.id == session_id).first()
    if not session_row:
        return None

    rows = (
        db.query(PalletStockCheck)
        .filter(PalletStockCheck.session_id == session_id)
        .order_by(PalletStockCheck.expected_in_system.desc(), PalletStockCheck.ma_cay.asc())
        .all()
    )
    detail_rows = [
        PalletAuditRow(
            ma_cay=row.ma_cay,
            nhu_cau=row.nhu_cau,
            lot=row.lot,
            system_yards=_to_float(row.system_yards),
            present_actual=bool(row.present_actual),
            expected_in_system=bool(row.expected_in_system),
            vi_tri_he_thong=row.vi_tri,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    return PalletAuditSessionDetail(
        session_id=session_row.id,
        created_at=session_row.created_at,
        vi_tri=session_row.vi_tri,
        app_roll_count=int(session_row.app_roll_count or 0),
        matched_roll_count=int(session_row.matched_roll_count or 0),
        extra_roll_count=int(session_row.extra_roll_count or 0),
        rows=detail_rows,
    )


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


def save_pallet_audit(
    db: Session,
    *,
    vi_tri: str,
    present_ma_cays: list[str],
    extra_ma_cays: list[str],
) -> int:
    vi_tri_s = (vi_tri or "").strip()
    if not vi_tri_s:
        return 0

    present_set = {str(ma or "").strip() for ma in present_ma_cays if str(ma or "").strip()}
    extra_set = {str(ma or "").strip() for ma in extra_ma_cays if str(ma or "").strip()}

    expected_rows = (
        db.query(LocationAssignment.ma_cay, LocationAssignment.nhu_cau, LocationAssignment.lot)
        .filter(LocationAssignment.vi_tri == vi_tri_s)
        .filter(LocationAssignment.trang_thai.in_(("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")))
        .all()
    )
    expected_map = {
        str(ma_cay): (str(nhu_cau) if nhu_cau else None, str(lot) if lot else None)
        for ma_cay, nhu_cau, lot in expected_rows
        if ma_cay
    }
    extra_set.difference_update(expected_map.keys())

    all_ma_cays = list(dict.fromkeys([*expected_map.keys(), *extra_set]))
    if not all_ma_cays:
        return 0

    system_yards_map = _effective_system_yards_map(db, ma_cays=all_ma_cays)

    values: list[dict] = []
    matched_roll_count = 0
    for ma_cay, (nhu_cau, lot) in expected_map.items():
        is_present = ma_cay in present_set
        if is_present:
            matched_roll_count += 1
        values.append(
            {
                "session_id": 0,
                "vi_tri": vi_tri_s,
                "ma_cay": ma_cay,
                "nhu_cau": nhu_cau,
                "lot": lot,
                "system_yards": system_yards_map.get(ma_cay),
                "expected_in_system": True,
                "present_actual": is_present,
            }
        )

    extra_assignments = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.ma_cay.in_(list(extra_set)) if extra_set else False)
        .filter(LocationAssignment.trang_thai.in_(("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")))
        .all()
    )
    extra_assignment_map = {str(row.ma_cay): row for row in extra_assignments if row.ma_cay}

    actual_extra_count = 0
    for ma_cay in extra_set:
        assignment = extra_assignment_map.get(ma_cay)
        if not assignment:
            continue
        actual_extra_count += 1
        values.append(
            {
                "session_id": 0,
                "vi_tri": vi_tri_s,
                "ma_cay": ma_cay,
                "nhu_cau": assignment.nhu_cau,
                "lot": assignment.lot,
                "system_yards": system_yards_map.get(ma_cay),
                "expected_in_system": False,
                "present_actual": True,
            }
        )
        from_vi_tri = assignment.vi_tri
        if from_vi_tri != vi_tri_s:
            assignment.vi_tri = vi_tri_s
            db.add(assignment)
            db.add(
                LocationTransferLog(
                    ma_cay=ma_cay,
                    nhu_cau=assignment.nhu_cau,
                    lot=assignment.lot,
                    from_vi_tri=from_vi_tri,
                    to_vi_tri=vi_tri_s,
                    note="pallet_stock_check_extra",
                )
            )

    if not values:
        return 0

    audit_session = PalletStockCheckSession(
        vi_tri=vi_tri_s,
        app_roll_count=len(expected_map),
        matched_roll_count=matched_roll_count,
        extra_roll_count=actual_extra_count,
    )
    db.add(audit_session)
    db.flush()

    for value in values:
        value["session_id"] = audit_session.id

    stmt = pg_insert(PalletStockCheck.__table__).values(values)
    res = db.execute(stmt)
    return int(res.rowcount or 0)
