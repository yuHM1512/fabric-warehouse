from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck

PALLET_CAPACITY_M3 = 1.5


@dataclass(frozen=True)
class InOutPoint:
    day: date
    in_m3: float
    out_m3: float
    in_yds: float
    out_yds: float


@dataclass(frozen=True)
class AgeSplit:
    under_6m_m3: float
    over_6m_m3: float

    @property
    def total_m3(self) -> float:
        return float(self.under_6m_m3 + self.over_6m_m3)


def _as_float(v: object, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return default


def _norm_key_candidates(code: str) -> list[str]:
    code = (code or "").strip()
    if not code:
        return []
    candidates = [code]
    try:
        as_int = int(float(code))
        candidates.append(str(as_int))
    except Exception:
        pass
    return list(dict.fromkeys(candidates))


def _get_yds_max(*, norms: dict[str, float], ma_art: str | None) -> float:
    if not ma_art or ma_art == "KHÔNG TÌM THẤY":
        return 2000.0

    for key in _norm_key_candidates(ma_art):
        y = norms.get(key)
        if y is not None and y > 0:
            return float(y)

    ma_art_s = str(ma_art)
    for k, v in norms.items():
        if (ma_art_s in str(k) or str(k) in ma_art_s) and v > 0:
            return float(v)

    return 2000.0


def _load_norms(db: Session) -> dict[str, float]:
    try:
        rows = (
            db.query(FabricData.ma_model, FabricData.yrd_per_pallet)
            .filter(FabricData.yrd_per_pallet.isnot(None))
            .filter(FabricData.yrd_per_pallet > 0)
            .all()
        )
        return {str(k): _as_float(v, 0.0) for k, v in rows if k}
    except Exception:
        # Allow dashboard to work even if norms table is not migrated yet.
        return {}


def _line_art_code(line: ReceiptLine) -> str | None:
    raw = line.raw_data or {}
    return (
        (str(line.art).strip() if line.art else "")
        or (str(line.model).strip() if line.model else "")
        or (str(raw.get("Mã Art") or raw.get("Ma Art") or raw.get("MÃ£ Art") or "").strip())
        or (str(raw.get("Mã Model") or raw.get("Ma Model") or raw.get("MÃ£ Model") or "").strip())
        or None
    )


def _m3_from_yards(*, yards: float, yds_max: float) -> float:
    if not yds_max or yds_max <= 0:
        yds_max = 2000.0
    ratio = float(yards) / float(yds_max) if yards else 0.0
    return ratio * PALLET_CAPACITY_M3


def list_in_out_by_day(db: Session, *, from_day: date, to_day: date) -> list[InOutPoint]:
    norms = _load_norms(db)

    days: list[date] = []
    d = from_day
    while d <= to_day:
        days.append(d)
        d += timedelta(days=1)

    in_map: dict[date, float] = {x: 0.0 for x in days}
    out_map: dict[date, float] = {x: 0.0 for x in days}
    in_yds_map: dict[date, float] = {x: 0.0 for x in days}
    out_yds_map: dict[date, float] = {x: 0.0 for x in days}

    # IN: use assigned_at from location_assignments (works even when only that table exists).
    # Yards: prefer stock_checks.actual_yards, fallback to receipt_lines.yards.
    try:
        assignments = (
            db.query(
                LocationAssignment.nhu_cau,
                LocationAssignment.lot,
                LocationAssignment.ma_cay,
                LocationAssignment.assigned_at,
            )
            .filter(func.date(LocationAssignment.assigned_at) >= from_day)
            .filter(func.date(LocationAssignment.assigned_at) <= to_day)
            .all()
        )
    except Exception:
        assignments = []

    ma_cays = sorted({str(a[2]) for a in assignments if a[2]})

    actual_map: dict[tuple[str, str, str], float] = {}
    actual_by_lot_ma: dict[tuple[str, str], float] = {}
    if ma_cays:
        try:
            sc_rows = (
                db.query(StockCheck.nhu_cau, StockCheck.lot, StockCheck.ma_cay, StockCheck.actual_yards)
                .filter(StockCheck.actual_yards.isnot(None))
                .filter(StockCheck.ma_cay.in_(ma_cays))
                .all()
            )
            for nc, lot, ma, actual in sc_rows:
                val = _as_float(actual, 0.0)
                actual_map[(str(nc), str(lot), str(ma))] = val
                actual_by_lot_ma[(str(lot), str(ma))] = val
        except Exception:
            actual_map = {}
            actual_by_lot_ma = {}

    receipt_map: dict[tuple[str, str, str], tuple[float, str | None]] = {}
    receipt_by_lot_ma: dict[tuple[str, str], tuple[float, str | None]] = {}
    if ma_cays:
        try:
            rl_rows = (
                db.query(
                    ReceiptLine.nhu_cau,
                    ReceiptLine.lot,
                    ReceiptLine.ma_cay,
                    ReceiptLine.yards,
                    ReceiptLine.art,
                    ReceiptLine.model,
                    ReceiptLine.raw_data,
                )
                .filter(ReceiptLine.ma_cay.in_(ma_cays))
                .all()
            )
            for nc, lot, ma, yards, art, model, raw in rl_rows:
                key = (str(nc), str(lot), str(ma))
                if key in receipt_map:
                    continue
                raw = raw or {}
                code = (
                    (str(art).strip() if art else "")
                    or (str(model).strip() if model else "")
                    or (str(raw.get("Mã Art") or raw.get("Ma Art") or raw.get("MÃ£ Art") or "").strip())
                    or (str(raw.get("Mã Model") or raw.get("Ma Model") or raw.get("MÃ£ Model") or "").strip())
                    or None
                )
                val = (_as_float(yards, 0.0), code)
                receipt_map[key] = val
                receipt_by_lot_ma[(str(lot), str(ma))] = val
        except Exception:
            receipt_map = {}
            receipt_by_lot_ma = {}

    for nc, lot, ma, assigned_at in assignments:
        day = assigned_at.date() if assigned_at else None
        if not day:
            continue
        key = (str(nc), str(lot), str(ma))
        yards = actual_map.get(key)
        if yards is None or yards <= 0:
            yards = actual_by_lot_ma.get((str(lot), str(ma)))
        if yards is None or yards <= 0:
            yards = receipt_map.get(key, (0.0, None))[0]
        if yards is None or yards <= 0:
            yards = receipt_by_lot_ma.get((str(lot), str(ma)), (0.0, None))[0]

        code = receipt_map.get(key, (0.0, None))[1]
        if not code:
            code = receipt_by_lot_ma.get((str(lot), str(ma)), (0.0, None))[1]
        yds_max = _get_yds_max(norms=norms, ma_art=code)
        in_map[day] = in_map.get(day, 0.0) + _m3_from_yards(yards=float(yards or 0.0), yds_max=yds_max)
        in_yds_map[day] = in_yds_map.get(day, 0.0) + float(yards or 0.0)

    try:
        out_rows = (
            db.query(Issue, IssueLine)
            .join(IssueLine, IssueLine.issue_id == Issue.id)
            .filter(func.date(Issue.created_at) >= from_day)
            .filter(func.date(Issue.created_at) <= to_day)
            .all()
        )
    except Exception:
        out_rows = []

    out_ma_cays = sorted({str(line.ma_cay) for issue, line in out_rows if line.ma_cay})
    ma_art_map: dict[str, str] = {}
    if out_ma_cays:
        rows = (
            db.query(ReceiptLine.ma_cay, ReceiptLine.art, ReceiptLine.model, ReceiptLine.raw_data)
            .filter(ReceiptLine.ma_cay.in_(out_ma_cays))
            .all()
        )
        for ma, art, model, raw in rows:
            if not ma or str(ma) in ma_art_map:
                continue
            raw = raw or {}
            code = (
                (str(art).strip() if art else "")
                or (str(model).strip() if model else "")
                or (str(raw.get("Mã Art") or raw.get("Ma Art") or raw.get("MÃ£ Art") or "").strip())
                or (str(raw.get("Mã Model") or raw.get("Ma Model") or raw.get("MÃ£ Model") or "").strip())
            )
            if code:
                ma_art_map[str(ma)] = code

    for issue, line in out_rows:
        day = issue.created_at.date() if issue.created_at else None
        if not day:
            continue
        yards = _as_float(line.so_luong_xuat, 0.0)
        yds_max = _get_yds_max(norms=norms, ma_art=ma_art_map.get(str(line.ma_cay)) if line.ma_cay else None)
        out_map[day] = out_map.get(day, 0.0) + _m3_from_yards(yards=yards, yds_max=yds_max)
        out_yds_map[day] = out_yds_map.get(day, 0.0) + float(yards)

    return [
        InOutPoint(
            day=x,
            in_m3=float(in_map.get(x, 0.0)),
            out_m3=float(out_map.get(x, 0.0)),
            in_yds=float(in_yds_map.get(x, 0.0)),
            out_yds=float(out_yds_map.get(x, 0.0)),
        )
        for x in days
    ]


def compute_age_split_for_stored(db: Session) -> AgeSplit:
    norms = _load_norms(db)

    try:
        stored = (
            db.query(
                LocationAssignment.nhu_cau,
                LocationAssignment.lot,
                LocationAssignment.ma_cay,
                LocationAssignment.assigned_at,
            )
            .filter(LocationAssignment.trang_thai == "Đang lưu")
            .all()
        )
    except Exception:
        stored = []

    ma_cays = sorted({str(r[2]) for r in stored if r[2]})
    if not ma_cays:
        return AgeSplit(under_6m_m3=0.0, over_6m_m3=0.0)

    min_day_map: dict[str, date] = {}
    try:
        min_rows = (
            db.query(
                ReceiptLine.ma_cay,
                func.min(func.coalesce(Receipt.receipt_date, func.date(Receipt.created_at))).label("min_day"),
            )
            .join(Receipt, Receipt.id == ReceiptLine.receipt_id)
            .filter(ReceiptLine.ma_cay.in_(ma_cays))
            .group_by(ReceiptLine.ma_cay)
            .all()
        )
        min_day_map = {str(ma): d for ma, d in min_rows if ma and d}
    except Exception:
        min_day_map = {}

    actual_map: dict[tuple[str, str, str], float] = {}
    actual_by_lot_ma: dict[tuple[str, str], float] = {}
    try:
        sc_rows = (
            db.query(StockCheck.nhu_cau, StockCheck.lot, StockCheck.ma_cay, StockCheck.actual_yards)
            .filter(StockCheck.actual_yards.isnot(None))
            .filter(StockCheck.ma_cay.in_(ma_cays))
            .all()
        )
        for nc, lot, ma, actual in sc_rows:
            val = _as_float(actual, 0.0)
            actual_map[(str(nc), str(lot), str(ma))] = val
            actual_by_lot_ma[(str(lot), str(ma))] = val
    except Exception:
        actual_map = {}
        actual_by_lot_ma = {}

    receipt_yards_map: dict[tuple[str, str, str], float] = {}
    receipt_yards_by_lot_ma: dict[tuple[str, str], float] = {}
    ma_art_map: dict[str, str] = {}
    try:
        art_rows = (
            db.query(
                ReceiptLine.nhu_cau,
                ReceiptLine.lot,
                ReceiptLine.ma_cay,
                ReceiptLine.yards,
                ReceiptLine.art,
                ReceiptLine.model,
                ReceiptLine.raw_data,
            )
            .filter(ReceiptLine.ma_cay.in_(ma_cays))
            .all()
        )
        for nc, lot, ma, yards, art, model, raw in art_rows:
            if not ma:
                continue
            raw = raw or {}
            code = (
                (str(art).strip() if art else "")
                or (str(model).strip() if model else "")
                or (str(raw.get("Mã Art") or raw.get("Ma Art") or raw.get("MÃ£ Art") or "").strip())
                or (str(raw.get("Mã Model") or raw.get("Ma Model") or raw.get("MÃ£ Model") or "").strip())
            )
            if code and str(ma) not in ma_art_map:
                ma_art_map[str(ma)] = code

            key = (str(nc), str(lot), str(ma))
            if key not in receipt_yards_map:
                val = _as_float(yards, 0.0)
                receipt_yards_map[key] = val
                receipt_yards_by_lot_ma[(str(lot), str(ma))] = val
    except Exception:
        receipt_yards_map = {}
        receipt_yards_by_lot_ma = {}
        ma_art_map = {}

    split_day = date.today() - timedelta(days=183)

    under_m3 = 0.0
    over_m3 = 0.0
    for nc, lot, ma, assigned_at in stored:
        ma_s = str(ma)
        day0 = min_day_map.get(ma_s)
        if not day0:
            day0 = assigned_at.date() if assigned_at else None
        if not day0:
            continue

        key = (str(nc), str(lot), ma_s)
        actual = actual_map.get(key)
        if actual is None or actual <= 0:
            actual = actual_by_lot_ma.get((str(lot), ma_s))
        if actual is None or actual <= 0:
            actual = receipt_yards_map.get(key, 0.0)
        if actual is None or actual <= 0:
            actual = receipt_yards_by_lot_ma.get((str(lot), ma_s), 0.0)

        yds_max = _get_yds_max(norms=norms, ma_art=ma_art_map.get(ma_s))
        vol = _m3_from_yards(yards=float(actual or 0.0), yds_max=yds_max)
        if day0 >= split_day:
            under_m3 += vol
        else:
            over_m3 += vol

    return AgeSplit(under_6m_m3=float(under_m3), over_6m_m3=float(over_m3))
