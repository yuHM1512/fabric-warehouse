from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.inventory_count_row import InventoryCountRow
from fabric_warehouse.db.models.inventory_count_session import InventoryCountSession
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck

_DANG_LUU_VARIANTS = ("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")


@dataclass(frozen=True)
class InventoryCountSessionSummary:
    session_id: int
    session_date: date
    status: str
    row_count: int
    counted_row_count: int
    created_at: datetime | None


@dataclass(frozen=True)
class InventoryCountPalletRow:
    vi_tri: str
    quantity: float
    roll_count: int


@dataclass(frozen=True)
class InventoryCountRowView:
    row_id: int
    ma_hang: str
    loai_vai: str
    ten_vai: str
    system_roll_count: int
    system_quantity: float
    pallet_rows: list[InventoryCountPalletRow]
    actual_quantity: float | None
    note: str | None
    updated_at: datetime | None

    @property
    def variance_quantity(self) -> float | None:
        if self.actual_quantity is None:
            return None
        return float(self.actual_quantity - self.system_quantity)

    @property
    def is_full_match(self) -> bool:
        return self.actual_quantity is not None and abs(self.actual_quantity - self.system_quantity) < 1e-9


@dataclass(frozen=True)
class InventoryCountMaHangGroup:
    ma_hang: str
    rows: list[InventoryCountRowView]

    @property
    def total_quantity(self) -> float:
        return float(sum(row.system_quantity for row in self.rows))

    @property
    def total_roll_count(self) -> int:
        return int(sum(row.system_roll_count for row in self.rows))

    @property
    def fabric_count(self) -> int:
        return len(self.rows)

    @property
    def counted_count(self) -> int:
        return sum(1 for row in self.rows if row.actual_quantity is not None or row.note)


@dataclass(frozen=True)
class InventoryCountSessionDetail:
    session_id: int
    session_date: date
    status: str
    row_count: int
    counted_row_count: int
    created_at: datetime | None
    groups: list[InventoryCountMaHangGroup]
    ma_hang_options: list[str]


def _yds_expr() -> object:
    return func.coalesce(StockCheck.actual_yards, StockCheck.expected_yards, ReceiptLine.yards, 0)


def _tag_subquery(db: Session):
    return (
        db.query(
            HangingTag.nhu_cau,
            HangingTag.lot,
            HangingTag.ma_hang,
            HangingTag.loai_vai,
            HangingTag.ma_art,
        )
        .distinct(HangingTag.nhu_cau, HangingTag.lot)
        .order_by(HangingTag.nhu_cau, HangingTag.lot, HangingTag.id)
        .subquery()
    )


def create_inventory_count_session(
    db: Session,
    *,
    session_date: date,
) -> InventoryCountSession:
    ht = _tag_subquery(db)
    rows = (
        db.query(
            func.coalesce(ht.c.ma_hang, "(Không xác định)").label("ma_hang"),
            func.coalesce(ht.c.loai_vai, "(Không xác định)").label("loai_vai"),
            func.coalesce(ht.c.ma_art, "(Không xác định)").label("ten_vai"),
            func.coalesce(LocationAssignment.vi_tri, "(Chưa gắn pallet)").label("vi_tri"),
            func.count(LocationAssignment.ma_cay).label("system_roll_count"),
            func.coalesce(func.sum(_yds_expr()), 0).label("system_quantity"),
        )
        .outerjoin(
            ht,
            and_(
                ht.c.nhu_cau == LocationAssignment.nhu_cau,
                ht.c.lot == LocationAssignment.lot,
            ),
        )
        .outerjoin(
            StockCheck,
            and_(
                StockCheck.ma_cay == LocationAssignment.ma_cay,
                StockCheck.nhu_cau == LocationAssignment.nhu_cau,
                StockCheck.lot == LocationAssignment.lot,
            ),
        )
        .outerjoin(ReceiptLine, ReceiptLine.ma_cay == LocationAssignment.ma_cay)
        .filter(LocationAssignment.trang_thai.in_(_DANG_LUU_VARIANTS))
        .group_by(ht.c.ma_hang, ht.c.loai_vai, ht.c.ma_art, LocationAssignment.vi_tri)
        .order_by(
            func.coalesce(ht.c.ma_hang, "(Không xác định)").asc(),
            func.coalesce(ht.c.loai_vai, "(Không xác định)").asc(),
            func.coalesce(ht.c.ma_art, "(Không xác định)").asc(),
            func.coalesce(LocationAssignment.vi_tri, "(Chưa gắn pallet)").asc(),
        )
        .all()
    )

    grouped_rows: dict[tuple[str, str, str], dict[str, object]] = {}
    for item in rows:
        key = (
            str(item.ma_hang or "").strip() or "(Không xác định)",
            str(item.loai_vai or "").strip() or "(Không xác định)",
            str(item.ten_vai or "").strip() or "(Không xác định)",
        )
        payload = grouped_rows.setdefault(
            key,
            {
                "system_roll_count": 0,
                "system_quantity": 0.0,
                "pallet_snapshot": [],
            },
        )
        payload["system_roll_count"] = int(payload["system_roll_count"]) + int(item.system_roll_count or 0)
        payload["system_quantity"] = float(payload["system_quantity"]) + float(item.system_quantity or 0)
        pallet_snapshot = payload["pallet_snapshot"]
        assert isinstance(pallet_snapshot, list)
        pallet_snapshot.append(
            {
                "vi_tri": str(item.vi_tri or "").strip() or "(Chưa gắn pallet)",
                "quantity": float(item.system_quantity or 0),
                "roll_count": int(item.system_roll_count or 0),
            }
        )

    session_row = InventoryCountSession(
        session_date=session_date,
        status="open",
        row_count=len(grouped_rows),
    )
    db.add(session_row)
    db.flush()

    if grouped_rows:
        db.bulk_save_objects(
            [
                InventoryCountRow(
                    session_id=session_row.id,
                    ma_hang=ma_hang,
                    loai_vai=loai_vai,
                    ten_vai=ten_vai,
                    system_roll_count=int(payload["system_roll_count"]),
                    system_quantity=float(payload["system_quantity"]),
                    pallet_snapshot=list(payload["pallet_snapshot"]),
                )
                for (ma_hang, loai_vai, ten_vai), payload in grouped_rows.items()
            ]
        )

    return session_row


def list_inventory_count_sessions(
    db: Session,
    *,
    limit: int = 30,
) -> list[InventoryCountSessionSummary]:
    counted_sq = (
        db.query(
            InventoryCountRow.session_id.label("session_id"),
            func.count(InventoryCountRow.id).label("counted_row_count"),
        )
        .filter(InventoryCountRow.actual_quantity.isnot(None))
        .group_by(InventoryCountRow.session_id)
        .subquery()
    )
    rows = (
        db.query(InventoryCountSession, counted_sq.c.counted_row_count)
        .outerjoin(counted_sq, counted_sq.c.session_id == InventoryCountSession.id)
        .order_by(InventoryCountSession.created_at.desc(), InventoryCountSession.id.desc())
        .limit(limit)
        .all()
    )
    return [
        InventoryCountSessionSummary(
            session_id=session_row.id,
            session_date=session_row.session_date,
            status=session_row.status,
            row_count=int(session_row.row_count or 0),
            counted_row_count=int(counted_row_count or 0),
            created_at=session_row.created_at,
        )
        for session_row, counted_row_count in rows
    ]


def get_inventory_count_session_detail(
    db: Session,
    *,
    session_id: int,
    ma_hang: str | None = None,
) -> InventoryCountSessionDetail | None:
    session_row = db.query(InventoryCountSession).filter(InventoryCountSession.id == session_id).first()
    if not session_row:
        return None

    options_rows = (
        db.query(InventoryCountRow.ma_hang)
        .filter(InventoryCountRow.session_id == session_id)
        .distinct()
        .order_by(InventoryCountRow.ma_hang.asc())
        .all()
    )
    ma_hang_options = [str(item[0]) for item in options_rows if item and item[0]]

    q = db.query(InventoryCountRow).filter(InventoryCountRow.session_id == session_id)
    ma_hang_s = (ma_hang or "").strip()
    if ma_hang_s:
        q = q.filter(InventoryCountRow.ma_hang == ma_hang_s)

    row_items = (
        q.order_by(
            InventoryCountRow.ma_hang.asc(),
            InventoryCountRow.loai_vai.asc(),
            InventoryCountRow.ten_vai.asc(),
            InventoryCountRow.id.asc(),
        ).all()
    )
    counted_row_count = (
        db.query(func.count(InventoryCountRow.id))
        .filter(InventoryCountRow.session_id == session_id)
        .filter(InventoryCountRow.actual_quantity.isnot(None))
        .scalar()
        or 0
    )

    row_views = [
        InventoryCountRowView(
            row_id=row.id,
            ma_hang=str(row.ma_hang or "").strip() or "(Không xác định)",
            loai_vai=str(row.loai_vai or "").strip() or "(Không xác định)",
            ten_vai=str(row.ten_vai or "").strip() or "(Không xác định)",
            system_roll_count=int(row.system_roll_count or 0),
            system_quantity=float(row.system_quantity or 0),
            pallet_rows=[
                InventoryCountPalletRow(
                    vi_tri=str(item.get("vi_tri") or "").strip() or "(Chưa gắn pallet)",
                    quantity=float(item.get("quantity") or 0),
                    roll_count=int(item.get("roll_count") or 0),
                )
                for item in list(row.pallet_snapshot or [])
            ],
            actual_quantity=float(row.actual_quantity) if row.actual_quantity is not None else None,
            note=row.note,
            updated_at=row.updated_at,
        )
        for row in row_items
    ]

    groups_map: dict[str, list[InventoryCountRowView]] = {}
    for row in row_views:
        groups_map.setdefault(row.ma_hang, []).append(row)

    groups = [
        InventoryCountMaHangGroup(ma_hang=ma_hang_key, rows=rows_for_ma_hang)
        for ma_hang_key, rows_for_ma_hang in groups_map.items()
    ]

    return InventoryCountSessionDetail(
        session_id=session_row.id,
        session_date=session_row.session_date,
        status=session_row.status,
        row_count=int(session_row.row_count or 0),
        counted_row_count=int(counted_row_count or 0),
        created_at=session_row.created_at,
        groups=groups,
        ma_hang_options=ma_hang_options,
    )


def update_inventory_count_rows(
    db: Session,
    *,
    session_id: int,
    items: list[dict[str, object]],
) -> int:
    row_ids = [int(item["row_id"]) for item in items if item.get("row_id")]
    if not row_ids:
        return 0

    rows = (
        db.query(InventoryCountRow)
        .filter(InventoryCountRow.session_id == session_id)
        .filter(InventoryCountRow.id.in_(row_ids))
        .all()
    )
    row_by_id = {row.id: row for row in rows}
    updated = 0
    for item in items:
        row_id = int(item["row_id"])
        row = row_by_id.get(row_id)
        if not row:
            continue
        row.actual_quantity = item.get("actual_quantity")  # type: ignore[assignment]
        row.note = item.get("note")  # type: ignore[assignment]
        updated += 1
    return updated
