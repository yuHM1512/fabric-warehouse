from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from fabric_warehouse.db.models.demand_transfer_log import DemandTransferLog
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent
from fabric_warehouse.db.models.stock_check import StockCheck

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class TraceEvent:
    at: datetime
    kind: str
    summary: str


def _dt_from_date(d: date | None) -> datetime | None:
    if not d:
        return None
    return datetime.combine(d, time(0, 0), tzinfo=timezone.utc)


def _dt_from_date_local(d: date | None) -> datetime | None:
    if not d:
        return None
    return datetime.combine(d, time(0, 0), tzinfo=VN_TZ)


def build_trace_timeline(db: Session, *, lot: str, ma_cay: str) -> list[TraceEvent]:
    lot = (lot or "").strip()
    ma_cay = (ma_cay or "").strip()
    if not lot or not ma_cay:
        return []

    events: list[TraceEvent] = []

    # Phiếu nhập (receipt line)
    rl = (
        db.query(ReceiptLine, Receipt)
        .join(Receipt, Receipt.id == ReceiptLine.receipt_id)
        .filter(ReceiptLine.lot == lot)
        .filter(ReceiptLine.ma_cay == ma_cay)
        .order_by(ReceiptLine.id.asc())
        .first()
    )
    if rl:
        line, receipt = rl
        at = receipt.created_at or line.created_at
        if at:
            events.append(
                TraceEvent(
                    at=at,
                    kind="Phiếu nhập",
                    summary=f"Receipt #{receipt.id} — Nhu cầu: {line.nhu_cau or ''}, Lot: {line.lot or ''}, YDS: {line.yards or ''}",
                )
            )

    # Nhập kho = timestamp đầu tiên gán vị trí (xác nhận lưu kho)
    first_loc = (
        db.query(LocationTransferLog)
        .filter(LocationTransferLog.ma_cay == ma_cay)
        .filter(LocationTransferLog.from_vi_tri.is_(None))
        .order_by(LocationTransferLog.created_at.asc())
        .first()
    )
    if first_loc and first_loc.created_at:
        events.append(
            TraceEvent(
                at=first_loc.created_at,
                kind="Nhập kho",
                summary=f"Xác nhận lưu kho tại {first_loc.to_vi_tri}",
            )
        )
    else:
        la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == ma_cay).first()
        fallback_at = la.assigned_at if (la and getattr(la, "assigned_at", None)) else (la.updated_at if (la and la.updated_at) else None)
        if fallback_at:
            events.append(
                TraceEvent(
                    at=fallback_at,
                    kind="Nhập kho",
                    summary=f"Xác nhận lưu kho (thiếu log) — {la.vi_tri}",
                )
            )

    # Stock check
    sc = (
        db.query(StockCheck)
        .filter(StockCheck.lot == lot)
        .filter(StockCheck.ma_cay == ma_cay)
        .order_by(StockCheck.updated_at.desc())
        .first()
    )
    if sc and sc.updated_at:
        events.append(
            TraceEvent(
                at=sc.updated_at,
                kind="Kiểm kho",
                summary=f"Thực tế: {sc.actual_yards or ''} (phiếu: {sc.expected_yards or ''}) — {sc.note or ''}".strip(),
            )
        )

    # Current position is derived from transfer logs; no separate "state" event.

    # Issue (export)
    il = (
        db.query(IssueLine, Issue)
        .join(Issue, Issue.id == IssueLine.issue_id)
        .filter(IssueLine.ma_cay == ma_cay)
        .filter(Issue.lot == lot)
        .order_by(Issue.created_at.asc(), Issue.id.asc())
        .all()
    )
    for line, issue in il:
        at = issue.created_at
        if not at:
            continue
        events.append(
            TraceEvent(
                at=at,
                kind="Xuất kho",
                summary=f"{issue.status or 'Cấp phát'} — YDS xuất: {line.so_luong_xuat or ''} — Vị trí: {line.vi_tri or ''} (issue #{issue.id})".strip(),
            )
        )

    # Return events (re-import)
    rets = (
        db.query(ReturnEvent)
        .filter(ReturnEvent.ma_cay == ma_cay)
        .order_by(ReturnEvent.ngay_tai_nhap.asc(), ReturnEvent.id.asc())
        .all()
    )
    for re in rets:
        at = _dt_from_date_local(re.ngay_tai_nhap) or re.created_at
        if not at:
            continue
        events.append(
            TraceEvent(
                at=at,
                kind="Tái nhập kho",
                summary=f"{re.status or ''} — YDS dư: {re.yds_du or ''} — NC/Lot mới: {(re.nhu_cau_moi or '')}/{(re.lot_moi or '')} — VT mới: {re.vi_tri_moi or ''}".strip(),
            )
        )

    # Demand transfer logs
    dtl = (
        db.query(DemandTransferLog)
        .filter(DemandTransferLog.ma_cay == ma_cay)
        .order_by(DemandTransferLog.created_at.desc())
        .all()
    )
    for it in dtl:
        events.append(
            TraceEvent(
                at=it.created_at,
                kind="Điều chuyển nhu cầu",
                summary=f"{it.from_nhu_cau or ''}/{it.from_lot or ''} → {it.to_nhu_cau}/{it.to_lot or ''} — {it.note or ''}".strip(),
            )
        )

    # Location transfer logs
    ltl = (
        db.query(LocationTransferLog)
        .filter(LocationTransferLog.ma_cay == ma_cay)
        .order_by(LocationTransferLog.created_at.desc())
        .all()
    )
    for it in ltl:
        if not it.from_vi_tri:
            continue
        events.append(
            TraceEvent(
                at=it.created_at,
                kind="Điều chuyển vị trí",
                summary=f"{it.from_vi_tri or ''} → {it.to_vi_tri} — {it.note or ''}".strip(),
            )
        )

    events.sort(key=lambda e: e.at)
    return events


def list_trace_lots(db: Session, *, limit: int = 2000) -> list[str]:
    rows = (
        db.query(ReceiptLine.lot)
        .filter(ReceiptLine.lot.isnot(None))
        .distinct()
        .order_by(ReceiptLine.lot.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_trace_ma_cays(db: Session, *, lot: str, limit: int = 5000) -> list[str]:
    lot = (lot or "").strip()
    if not lot:
        return []
    rows = (
        db.query(ReceiptLine.ma_cay)
        .filter(ReceiptLine.lot == lot)
        .filter(ReceiptLine.ma_cay.isnot(None))
        .distinct()
        .order_by(ReceiptLine.ma_cay.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def transfer_demand(
    db: Session,
    *,
    ma_cays: list[str],
    to_nhu_cau: str,
    to_lot: str | None,
    note: str | None,
) -> int:
    to_nhu_cau = (to_nhu_cau or "").strip()
    if not to_nhu_cau:
        return 0
    to_lot = (to_lot or "").strip() or None

    changed = 0
    for ma in ma_cays:
        ma = (ma or "").strip()
        if not ma:
            continue

        la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == ma).first()
        from_nhu_cau = la.nhu_cau if la else None
        from_lot = la.lot if la else None

        if la:
            la.nhu_cau = to_nhu_cau
            if to_lot:
                la.lot = to_lot
            db.add(la)

        # Update stock_check key for the roll (best effort: update rows with same ma_cay + from fields)
        q = db.query(StockCheck).filter(StockCheck.ma_cay == ma)
        if from_nhu_cau:
            q = q.filter(StockCheck.nhu_cau == from_nhu_cau)
        if from_lot:
            q = q.filter(StockCheck.lot == from_lot)
        for sc in q.all():
            sc.nhu_cau = to_nhu_cau
            if to_lot:
                sc.lot = to_lot
            db.add(sc)

        db.add(
            DemandTransferLog(
                ma_cay=ma,
                from_nhu_cau=from_nhu_cau,
                from_lot=from_lot,
                to_nhu_cau=to_nhu_cau,
                to_lot=to_lot,
                note=note,
            )
        )
        changed += 1

    return changed


def transfer_location(
    db: Session,
    *,
    ma_cays: list[str],
    to_vi_tri: str,
    note: str | None,
) -> int:
    to_vi_tri = (to_vi_tri or "").strip()
    if not to_vi_tri:
        return 0

    changed = 0
    for ma in ma_cays:
        ma = (ma or "").strip()
        if not ma:
            continue
        la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == ma).first()
        if not la:
            continue
        from_vi_tri = la.vi_tri
        la.vi_tri = to_vi_tri
        db.add(la)
        db.add(
            LocationTransferLog(
                ma_cay=ma,
                nhu_cau=la.nhu_cau,
                lot=la.lot,
                from_vi_tri=from_vi_tri,
                to_vi_tri=to_vi_tri,
                note=note,
            )
        )
        changed += 1
    return changed
