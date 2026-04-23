from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck

_DANG_LUU = "Đang lưu"
_DANG_LUU_VARIANTS = ("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")


@dataclass
class TonKhoRow:
    nhom: str
    nhom_phu: str | None
    so_cay: int
    tong_yds: float
    da_dinh_danh: int


@dataclass(frozen=True)
class AgeSplitKpis:
    under_rolls: int
    under_yds: float
    over_rolls: int
    over_yds: float

    @property
    def total_rolls(self) -> int:
        return int(self.under_rolls + self.over_rolls)

    @property
    def total_yds(self) -> float:
        return float(self.under_yds + self.over_yds)


@dataclass(frozen=True)
class StockAgeRow:
    nhu_cau: str
    lot: str
    ma_cay: str
    so_luong: float | None
    thuc_te: float | None
    ghi_chu: str | None
    vi_tri: str | None
    trang_thai: str | None
    ngay_cap_nhat: datetime | None
    assigned_at: datetime | None
    age_days: int | None
    bucket: str  # "under_6m" | "over_6m" | "unknown"


def _yds(sc: type) -> object:
    return func.coalesce(sc.actual_yards, sc.expected_yards)


def ton_kho_by_nhu_cau(db: Session) -> list[TonKhoRow]:
    rows = (
        db.query(
            LocationAssignment.nhu_cau.label("nhom"),
            func.count(LocationAssignment.ma_cay).label("so_cay"),
            func.coalesce(func.sum(_yds(StockCheck)), 0).label("tong_yds"),
            func.count(LocationAssignment.vi_tri).label("da_dinh_danh"),
        )
        .outerjoin(StockCheck, StockCheck.ma_cay == LocationAssignment.ma_cay)
        .filter(LocationAssignment.trang_thai == _DANG_LUU)
        .group_by(LocationAssignment.nhu_cau)
        .order_by(LocationAssignment.nhu_cau)
        .all()
    )
    return [
        TonKhoRow(
            nhom=r.nhom or "(Không xác định)",
            nhom_phu=None,
            so_cay=r.so_cay,
            tong_yds=float(r.tong_yds or 0),
            da_dinh_danh=r.da_dinh_danh,
        )
        for r in rows
    ]


def ton_kho_by_lot(db: Session) -> list[TonKhoRow]:
    rows = (
        db.query(
            LocationAssignment.lot.label("nhom"),
            LocationAssignment.nhu_cau.label("nhom_phu"),
            func.count(LocationAssignment.ma_cay).label("so_cay"),
            func.coalesce(func.sum(_yds(StockCheck)), 0).label("tong_yds"),
            func.count(LocationAssignment.vi_tri).label("da_dinh_danh"),
        )
        .outerjoin(StockCheck, StockCheck.ma_cay == LocationAssignment.ma_cay)
        .filter(LocationAssignment.trang_thai == _DANG_LUU)
        .group_by(LocationAssignment.lot, LocationAssignment.nhu_cau)
        .order_by(LocationAssignment.nhu_cau, LocationAssignment.lot)
        .all()
    )
    return [
        TonKhoRow(
            nhom=r.nhom or "(Không xác định)",
            nhom_phu=r.nhom_phu or None,
            so_cay=r.so_cay,
            tong_yds=float(r.tong_yds or 0),
            da_dinh_danh=r.da_dinh_danh,
        )
        for r in rows
    ]


def _ht_subquery(db: Session, *extra_cols):
    """One hanging_tag row per (nhu_cau, lot) — lowest id wins."""
    return (
        db.query(HangingTag.nhu_cau, HangingTag.lot, *extra_cols)
        .distinct(HangingTag.nhu_cau, HangingTag.lot)
        .order_by(HangingTag.nhu_cau, HangingTag.lot, HangingTag.id)
        .subquery()
    )


def ton_kho_by_loai_vai(db: Session) -> list[TonKhoRow]:
    ht = _ht_subquery(db, HangingTag.loai_vai)
    rows = (
        db.query(
            func.coalesce(ht.c.loai_vai, "(Không xác định)").label("nhom"),
            func.count(LocationAssignment.ma_cay).label("so_cay"),
            func.coalesce(func.sum(_yds(StockCheck)), 0).label("tong_yds"),
            func.count(LocationAssignment.vi_tri).label("da_dinh_danh"),
        )
        .outerjoin(ht, (ht.c.nhu_cau == LocationAssignment.nhu_cau) & (ht.c.lot == LocationAssignment.lot))
        .outerjoin(StockCheck, StockCheck.ma_cay == LocationAssignment.ma_cay)
        .filter(LocationAssignment.trang_thai == _DANG_LUU)
        .group_by(ht.c.loai_vai)
        .order_by(ht.c.loai_vai)
        .all()
    )
    return [
        TonKhoRow(
            nhom=r.nhom or "(Không xác định)",
            nhom_phu=None,
            so_cay=r.so_cay,
            tong_yds=float(r.tong_yds or 0),
            da_dinh_danh=r.da_dinh_danh,
        )
        for r in rows
    ]


def ton_kho_by_mau_vai(db: Session) -> list[TonKhoRow]:
    ht = _ht_subquery(db, HangingTag.mau_vai, HangingTag.ma_mau)
    rows = (
        db.query(
            func.coalesce(ht.c.mau_vai, "(Không xác định)").label("nhom"),
            func.coalesce(ht.c.ma_mau, "").label("nhom_phu"),
            func.count(LocationAssignment.ma_cay).label("so_cay"),
            func.coalesce(func.sum(_yds(StockCheck)), 0).label("tong_yds"),
            func.count(LocationAssignment.vi_tri).label("da_dinh_danh"),
        )
        .outerjoin(ht, (ht.c.nhu_cau == LocationAssignment.nhu_cau) & (ht.c.lot == LocationAssignment.lot))
        .outerjoin(StockCheck, StockCheck.ma_cay == LocationAssignment.ma_cay)
        .filter(LocationAssignment.trang_thai == _DANG_LUU)
        .group_by(ht.c.mau_vai, ht.c.ma_mau)
        .order_by(ht.c.mau_vai)
        .all()
    )
    return [
        TonKhoRow(
            nhom=r.nhom or "(Không xác định)",
            nhom_phu=r.nhom_phu or None,
            so_cay=r.so_cay,
            tong_yds=float(r.tong_yds or 0),
            da_dinh_danh=r.da_dinh_danh,
        )
        for r in rows
    ]


def ton_kho_by_age_split(
    db: Session,
    *,
    limit: int = 5000,
    split_days: int = 183,
    bucket: str | None = None,  # "under_6m" | "over_6m" | None
    nhu_cau: str | None = None,
    lot: str | None = None,
    sort: str = "nearest",  # "nearest" | "farthest"
) -> tuple[AgeSplitKpis, list[StockAgeRow]]:
    """
    Rolls currently stored, split into 2 buckets:
    - under_6m: assigned_at >= now - split_days
    - over_6m:  assigned_at <  now - split_days

    Uses LocationAssignment.assigned_at as the stored-confirmation timestamp.
    """
    now = datetime.now(timezone.utc)
    split_at = now - timedelta(days=int(split_days))

    q = (
        db.query(LocationAssignment, StockCheck)
        .outerjoin(
            StockCheck,
            and_(
                StockCheck.ma_cay == LocationAssignment.ma_cay,
                StockCheck.nhu_cau == LocationAssignment.nhu_cau,
                StockCheck.lot == LocationAssignment.lot,
            ),
        )
        .filter(LocationAssignment.trang_thai == _DANG_LUU)
    )

    if nhu_cau:
        q = q.filter(LocationAssignment.nhu_cau == nhu_cau)
    if lot:
        q = q.filter(LocationAssignment.lot == lot)

    if bucket == "under_6m":
        q = q.filter(LocationAssignment.assigned_at.isnot(None)).filter(LocationAssignment.assigned_at >= split_at)
    elif bucket == "over_6m":
        q = q.filter(LocationAssignment.assigned_at.isnot(None)).filter(LocationAssignment.assigned_at < split_at)

    if sort == "farthest":
        q = q.order_by(LocationAssignment.assigned_at.asc().nulls_last(), LocationAssignment.updated_at.desc())
    else:
        q = q.order_by(LocationAssignment.assigned_at.desc().nulls_last(), LocationAssignment.updated_at.desc())

    pairs = q.limit(limit).all()

    under_rolls = 0
    over_rolls = 0
    under_yds = 0.0
    over_yds = 0.0

    out: list[StockAgeRow] = []
    for la, sc in pairs:
        nhu_cau = str(la.nhu_cau or "").strip()
        lot = str(la.lot or "").strip()
        ma_cay = str(la.ma_cay or "").strip()

        so_luong = float(sc.expected_yards) if (sc and sc.expected_yards is not None) else None
        thuc_te = float(sc.actual_yards) if (sc and sc.actual_yards is not None) else None
        ghi_chu = (sc.note if sc else None) or None

        vi_tri = str(la.vi_tri).strip() if la.vi_tri is not None else None
        trang_thai = str(la.trang_thai).strip() if la.trang_thai is not None else None

        assigned_at = getattr(la, "assigned_at", None)
        updated_at = getattr(la, "updated_at", None) or (getattr(sc, "updated_at", None) if sc else None)

        age_days: int | None = None
        bucket = "unknown"
        yds_val = (thuc_te if thuc_te is not None else so_luong) or 0.0

        if isinstance(assigned_at, datetime):
            try:
                age_days = int((now - assigned_at.astimezone(timezone.utc)).days)
            except Exception:
                age_days = None

            if assigned_at < split_at:
                bucket = "over_6m"
                over_rolls += 1
                over_yds += float(yds_val)
            else:
                bucket = "under_6m"
                under_rolls += 1
                under_yds += float(yds_val)

        out.append(
            StockAgeRow(
                nhu_cau=nhu_cau,
                lot=lot,
                ma_cay=ma_cay,
                so_luong=so_luong,
                thuc_te=thuc_te,
                ghi_chu=ghi_chu,
                vi_tri=vi_tri,
                trang_thai=trang_thai,
                ngay_cap_nhat=updated_at,
                assigned_at=assigned_at,
                age_days=age_days,
                bucket=bucket,
            )
        )

    return (
        AgeSplitKpis(
            under_rolls=int(under_rolls),
            under_yds=float(under_yds),
            over_rolls=int(over_rolls),
            over_yds=float(over_yds),
        ),
        out,
    )


@dataclass(frozen=True)
class InboundLotRow:
    nhu_cau: str
    lot: str
    so_cay: int
    da_nhap_cay: int
    tong_yds: float
    da_nhap_yds: float
    vi_tri_list: str | None


@dataclass(frozen=True)
class InboundDemandGroup:
    nhu_cau: str
    lots: list[InboundLotRow]

    @property
    def rowspan(self) -> int:
        return len(self.lots)


def inbound_status_by_nhu_cau(
    db: Session,
    *,
    nhu_cau: str | None = None,
    limit_lots: int = 5000,
) -> list[InboundDemandGroup]:
    """
    Import/stock-check status grouped by Nhu cầu → Lot.

    - Total rolls/YDS are sourced from receipt_lines (dedup by (nhu_cau, lot, ma_cay)).
    - "Đã nhập" is sourced from stock_checks (presence of row = checked).
    """
    rr = (
        db.query(
            ReceiptLine.nhu_cau.label("nhu_cau"),
            ReceiptLine.lot.label("lot"),
            ReceiptLine.ma_cay.label("ma_cay"),
            func.max(ReceiptLine.id).label("rid"),
        )
        .filter(ReceiptLine.nhu_cau.isnot(None))
        .filter(ReceiptLine.lot.isnot(None))
        .group_by(ReceiptLine.nhu_cau, ReceiptLine.lot, ReceiptLine.ma_cay)
        .subquery()
    )
    rl = db.query(ReceiptLine).subquery()

    vi_tri_agg = func.string_agg(func.distinct(LocationAssignment.vi_tri), ", ").filter(
        and_(
            LocationAssignment.vi_tri.isnot(None),
            LocationAssignment.trang_thai.in_(_DANG_LUU_VARIANTS),
        )
    )

    q = (
        db.query(
            rr.c.nhu_cau,
            rr.c.lot,
            func.count(rr.c.ma_cay).label("so_cay"),
            func.count(func.distinct(StockCheck.ma_cay)).label("da_nhap_cay"),
            func.coalesce(func.sum(func.coalesce(rl.c.yards, 0)), 0).label("tong_yds"),
            func.coalesce(
                func.sum(func.coalesce(StockCheck.actual_yards, StockCheck.expected_yards, 0)),
                0,
            ).label("da_nhap_yds"),
            vi_tri_agg.label("vi_tri_list"),
        )
        .join(rl, rl.c.id == rr.c.rid)
        .outerjoin(
            StockCheck,
            and_(
                StockCheck.ma_cay == rr.c.ma_cay,
                StockCheck.nhu_cau == rr.c.nhu_cau,
                StockCheck.lot == rr.c.lot,
            ),
        )
        .outerjoin(
            LocationAssignment,
            and_(
                LocationAssignment.ma_cay == rr.c.ma_cay,
                LocationAssignment.nhu_cau == rr.c.nhu_cau,
                LocationAssignment.lot == rr.c.lot,
            ),
        )
    )
    if nhu_cau:
        q = q.filter(rr.c.nhu_cau == nhu_cau)

    rows = (
        q.group_by(rr.c.nhu_cau, rr.c.lot)
        .order_by(rr.c.nhu_cau, rr.c.lot)
        .limit(int(limit_lots))
        .all()
    )

    grouped: dict[str, list[InboundLotRow]] = {}
    for nc, lt, so_cay, da_nhap_cay, tong_yds, da_nhap_yds, vi_tri_list in rows:
        nc_s = str(nc or "").strip() or "(Không xác định)"
        lt_s = str(lt or "").strip() or "(Không xác định)"
        grouped.setdefault(nc_s, []).append(
            InboundLotRow(
                nhu_cau=nc_s,
                lot=lt_s,
                so_cay=int(so_cay or 0),
                da_nhap_cay=int(da_nhap_cay or 0),
                tong_yds=float(tong_yds or 0),
                da_nhap_yds=float(da_nhap_yds or 0),
                vi_tri_list=(str(vi_tri_list).strip() if vi_tri_list else None),
            )
        )

    return [InboundDemandGroup(nhu_cau=nc, lots=lots) for nc, lots in grouped.items()]


def list_active_inbound_nhu_cau_options(db: Session, *, limit: int = 5000) -> list[str]:
    """
    Active demands = have receipt_lines and (still pending stock check OR already stored).
    """
    rr = (
        db.query(
            ReceiptLine.nhu_cau.label("nhu_cau"),
            ReceiptLine.ma_cay.label("ma_cay"),
            func.max(ReceiptLine.id).label("rid"),
        )
        .filter(ReceiptLine.nhu_cau.isnot(None))
        .group_by(ReceiptLine.nhu_cau, ReceiptLine.ma_cay)
        .subquery()
    )

    totals = (
        db.query(
            rr.c.nhu_cau.label("nhu_cau"),
            func.count(rr.c.ma_cay).label("total_rolls"),
        )
        .group_by(rr.c.nhu_cau)
        .subquery()
    )

    checked = (
        db.query(
            StockCheck.nhu_cau.label("nhu_cau"),
            func.count(func.distinct(StockCheck.ma_cay)).label("checked_rolls"),
        )
        .group_by(StockCheck.nhu_cau)
        .subquery()
    )

    stored = (
        db.query(
            LocationAssignment.nhu_cau.label("nhu_cau"),
            func.count(func.distinct(LocationAssignment.ma_cay)).label("stored_rolls"),
        )
        .filter(LocationAssignment.trang_thai.in_(_DANG_LUU_VARIANTS))
        .group_by(LocationAssignment.nhu_cau)
        .subquery()
    )

    rows = (
        db.query(totals.c.nhu_cau)
        .outerjoin(checked, checked.c.nhu_cau == totals.c.nhu_cau)
        .outerjoin(stored, stored.c.nhu_cau == totals.c.nhu_cau)
        .filter(
            or_(
                func.coalesce(checked.c.checked_rolls, 0) < func.coalesce(totals.c.total_rolls, 0),
                func.coalesce(stored.c.stored_rolls, 0) > 0,
            )
        )
        .order_by(totals.c.nhu_cau)
        .limit(int(limit))
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]
