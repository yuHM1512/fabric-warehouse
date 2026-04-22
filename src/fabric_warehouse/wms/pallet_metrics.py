from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck

PALLET_CAPACITY_M3 = 1.5
STORED_STATUS = "Đang lưu"
APP_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class PalletKpis:
    total_pallets: int
    total_capacity_m3: float
    total_used_m3: float
    available_m3: float
    available_percent: float
    pallets_has_fabric: int


@dataclass(frozen=True)
class PalletCell:
    vi_tri: str
    used_percent: float
    roll_count: int


@dataclass(frozen=True)
class PalletLayoutLine:
    line: str
    pallets: list[str]


@dataclass(frozen=True)
class PalletLayout:
    tangs: list[str]
    lines: list[PalletLayoutLine]
    cells: dict[str, PalletCell]  # vi_tri -> cell


@dataclass(frozen=True)
class PalletRollRow:
    ma_cay: str
    nhu_cau: str
    lot: str
    yds: float | None
    ngay_nhap: str | None  # YYYY-MM-DD
    days_in_stock: int | None


def _chunks(items: list[str], *, size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


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


def _layout_lines() -> list[PalletLayoutLine]:
    lines = ["01", "02", "03"]

    def pallets_for_line(line: str) -> list[str]:
        if line == "01":
            return [f"{i:02d}" for i in range(1, 13)]
        return [f"{i:02d}" for i in range(1, 11)]

    return [PalletLayoutLine(line=l, pallets=pallets_for_line(l)) for l in lines]


def _compute_pallet_ratio_map(db: Session) -> dict[str, float]:
    assignments = (
        db.query(
            LocationAssignment.vi_tri,
            LocationAssignment.nhu_cau,
            LocationAssignment.lot,
            LocationAssignment.ma_cay,
        )
        .filter(LocationAssignment.trang_thai == STORED_STATUS)
        .all()
    )
    ma_cays = sorted({a.ma_cay for a in assignments if a.ma_cay})

    sc_rows = (
        db.query(StockCheck.nhu_cau, StockCheck.lot, StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.actual_yards.isnot(None))
        .filter(StockCheck.ma_cay.in_(ma_cays) if ma_cays else True)
        .all()
    )
    actual_map: dict[tuple[str, str, str], float] = {}
    for nc, lot, ma, actual in sc_rows:
        actual_map[(str(nc), str(lot), str(ma))] = _as_float(actual, 0.0)

    norm_rows = (
        db.query(FabricData.ma_model, FabricData.yrd_per_pallet)
        .filter(FabricData.yrd_per_pallet.isnot(None))
        .filter(FabricData.yrd_per_pallet > 0)
        .all()
    )
    norms: dict[str, float] = {str(k): _as_float(v, 0.0) for k, v in norm_rows if k}

    art_map: dict[str, str] = {}
    if ma_cays:
        for chunk in _chunks(ma_cays, size=800):
            rows = (
                db.query(ReceiptLine.ma_cay, ReceiptLine.art, ReceiptLine.model, ReceiptLine.raw_data)
                .filter(ReceiptLine.ma_cay.in_(chunk))
                .all()
            )
            for ma, art, model, raw in rows:
                if not ma or str(ma) in art_map:
                    continue
                raw = raw or {}
                code = (
                    (str(art).strip() if art else "")
                    or (str(model).strip() if model else "")
                    or (str(raw.get("MÃ£ Art") or raw.get("Ma Art") or raw.get("MÃƒÂ£ Art") or "").strip())
                    or (str(raw.get("MÃ£ Model") or raw.get("Ma Model") or raw.get("MÃƒÂ£ Model") or "").strip())
                )
                if code:
                    art_map[str(ma)] = code

    pallet_ratio: dict[str, float] = {}
    for vi_tri, nc, lot, ma in assignments:
        vi_tri_s = str(vi_tri or "").strip()
        if not vi_tri_s:
            continue
        actual = actual_map.get((str(nc), str(lot), str(ma)), 0.0)
        yds_max = _get_yds_max(norms=norms, ma_art=art_map.get(str(ma)))
        pallet_ratio[vi_tri_s] = pallet_ratio.get(vi_tri_s, 0.0) + (float(actual) / float(yds_max))

    return pallet_ratio


def compute_pallet_kpis(db: Session) -> PalletKpis:
    tangs = ["A", "B", "C"]
    lines = ["01", "02", "03"]

    def pallets_for_line(line: str) -> list[str]:
        if line == "01":
            return [f"{i:02d}" for i in range(1, 13)]
        return [f"{i:02d}" for i in range(1, 11)]

    total_pallets = len(tangs) * sum(len(pallets_for_line(l)) for l in lines)
    total_capacity_m3 = total_pallets * PALLET_CAPACITY_M3

    assignments = (
        db.query(
            LocationAssignment.vi_tri,
            LocationAssignment.nhu_cau,
            LocationAssignment.lot,
            LocationAssignment.ma_cay,
        )
        .filter(LocationAssignment.trang_thai == STORED_STATUS)
        .all()
    )
    pallets_has_fabric = len({a.vi_tri for a in assignments if a.vi_tri})
    ma_cays = sorted({a.ma_cay for a in assignments if a.ma_cay})

    sc_rows = (
        db.query(StockCheck.nhu_cau, StockCheck.lot, StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.actual_yards.isnot(None))
        .filter(StockCheck.ma_cay.in_(ma_cays) if ma_cays else True)
        .all()
    )
    actual_map: dict[tuple[str, str, str], float] = {}
    for nc, lot, ma, actual in sc_rows:
        actual_map[(str(nc), str(lot), str(ma))] = _as_float(actual, 0.0)

    norm_rows = (
        db.query(FabricData.ma_model, FabricData.yrd_per_pallet)
        .filter(FabricData.yrd_per_pallet.isnot(None))
        .filter(FabricData.yrd_per_pallet > 0)
        .all()
    )
    norms: dict[str, float] = {str(k): _as_float(v, 0.0) for k, v in norm_rows if k}

    art_map: dict[str, str] = {}
    if ma_cays:
        for chunk in _chunks(ma_cays, size=800):
            rows = (
                db.query(ReceiptLine.ma_cay, ReceiptLine.art, ReceiptLine.model, ReceiptLine.raw_data)
                .filter(ReceiptLine.ma_cay.in_(chunk))
                .all()
            )
            for ma, art, model, raw in rows:
                if not ma or str(ma) in art_map:
                    continue
                raw = raw or {}
                code = (
                    (str(art).strip() if art else "")
                    or (str(model).strip() if model else "")
                    or (str(raw.get("Mã Art") or raw.get("Ma Art") or raw.get("MÃ£ Art") or "").strip())
                    or (str(raw.get("Mã Model") or raw.get("Ma Model") or raw.get("MÃ£ Model") or "").strip())
                )
                if code:
                    art_map[str(ma)] = code

    pallet_ratio: dict[str, float] = {}
    for vi_tri, nc, lot, ma in assignments:
        vi_tri_s = str(vi_tri or "").strip()
        if not vi_tri_s:
            continue
        actual = actual_map.get((str(nc), str(lot), str(ma)), 0.0)
        yds_max = _get_yds_max(norms=norms, ma_art=art_map.get(str(ma)))
        pallet_ratio[vi_tri_s] = pallet_ratio.get(vi_tri_s, 0.0) + (float(actual) / float(yds_max))

    total_used_m3 = sum(r * PALLET_CAPACITY_M3 for r in pallet_ratio.values())
    available_m3 = total_capacity_m3 - total_used_m3
    available_percent = (available_m3 / total_capacity_m3 * 100.0) if total_capacity_m3 > 0 else 0.0

    return PalletKpis(
        total_pallets=int(total_pallets),
        total_capacity_m3=float(total_capacity_m3),
        total_used_m3=float(total_used_m3),
        available_m3=float(available_m3),
        available_percent=float(available_percent),
        pallets_has_fabric=int(pallets_has_fabric),
    )


def build_pallet_layout(db: Session) -> PalletLayout:
    tangs = ["A", "B", "C"]
    lines = _layout_lines()

    ratio_map = _compute_pallet_ratio_map(db)

    counts = (
        db.query(LocationAssignment.vi_tri)
        .filter(LocationAssignment.trang_thai == STORED_STATUS)
        .filter(LocationAssignment.vi_tri.isnot(None))
        .all()
    )
    roll_count_map: dict[str, int] = {}
    for (vi_tri,) in counts:
        key = str(vi_tri or "").strip()
        if not key:
            continue
        roll_count_map[key] = roll_count_map.get(key, 0) + 1

    cells: dict[str, PalletCell] = {}
    for tang in tangs:
        for l in lines:
            for p in l.pallets:
                vi_tri = f"{tang}.{l.line}.{p}"
                used_percent = float(ratio_map.get(vi_tri, 0.0) * 100.0)
                if used_percent < 0:
                    used_percent = 0.0
                if used_percent > 100:
                    used_percent = 100.0
                cells[vi_tri] = PalletCell(
                    vi_tri=vi_tri,
                    used_percent=used_percent,
                    roll_count=int(roll_count_map.get(vi_tri, 0)),
                )

    return PalletLayout(tangs=tangs, lines=lines, cells=cells)


def list_pallet_roll_rows(db: Session, *, vi_tri: str) -> list[PalletRollRow]:
    vi_tri_s = (vi_tri or "").strip()
    if not vi_tri_s:
        return []

    assignments = (
        db.query(
            LocationAssignment.ma_cay,
            LocationAssignment.nhu_cau,
            LocationAssignment.lot,
            LocationAssignment.assigned_at,
            LocationAssignment.updated_at,
        )
        .filter(LocationAssignment.trang_thai == STORED_STATUS)
        .filter(LocationAssignment.vi_tri == vi_tri_s)
        .order_by(LocationAssignment.ma_cay.asc())
        .all()
    )
    ma_cays = [str(ma) for ma, _, _, _, _ in assignments if ma]
    if not ma_cays:
        return []

    sc_rows = (
        db.query(StockCheck.nhu_cau, StockCheck.lot, StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.actual_yards.isnot(None))
        .filter(StockCheck.ma_cay.in_(ma_cays))
        .all()
    )
    actual_map: dict[tuple[str, str, str], float] = {}
    for nc, lot, ma, actual in sc_rows:
        actual_map[(str(nc), str(lot), str(ma))] = _as_float(actual, 0.0)

    receipt_rows = (
        db.query(ReceiptLine.ma_cay, Receipt.receipt_date, Receipt.created_at, ReceiptLine.created_at, ReceiptLine.yards)
        .join(Receipt, Receipt.id == ReceiptLine.receipt_id)
        .filter(ReceiptLine.ma_cay.in_(ma_cays))
        .order_by(ReceiptLine.created_at.desc())
        .all()
    )
    receipt_map: dict[str, tuple[str | None, float | None]] = {}
    for ma, receipt_date, receipt_created, line_created, yards in receipt_rows:
        ma_s = str(ma or "").strip()
        if not ma_s or ma_s in receipt_map:
            continue
        d = (
            receipt_date
            or (receipt_created.date() if receipt_created else None)
            or (line_created.date() if line_created else None)
        )
        receipt_map[ma_s] = (
            d.isoformat() if d else None,
            _as_float(yards, 0.0) if yards is not None else None,
        )

    now = datetime.now(timezone.utc)
    now_local = now.astimezone(APP_TZ)
    out: list[PalletRollRow] = []
    for ma, nc, lot, assigned_at, updated_at in assignments:
        ma_s = str(ma)
        nc_s = str(nc)
        lot_s = str(lot)
        ngay_nhap, yards = receipt_map.get(ma_s, (None, None))

        yds = actual_map.get((nc_s, lot_s, ma_s))
        if yds is None or yds == 0.0:
            yds = yards

        confirmed_at = assigned_at or updated_at
        confirmed_str: str | None = None
        days_in_stock: int | None = None
        if confirmed_at is not None:
            local = confirmed_at.astimezone(APP_TZ)
            confirmed_str = local.strftime("%Y-%m-%d %H:%M")
            days_in_stock = (now_local.date() - local.date()).days
            if days_in_stock < 0:
                days_in_stock = 0

        out.append(
            PalletRollRow(
                ma_cay=ma_s,
                nhu_cau=nc_s,
                lot=lot_s,
                yds=yds,
                ngay_nhap=confirmed_str,
                days_in_stock=days_in_stock,
            )
        )

    return out
