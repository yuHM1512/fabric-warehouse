from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent
from fabric_warehouse.db.models.stock_check import StockCheck


@dataclass(frozen=True)
class ReturnCandidateRow:
    issue_line_id: int
    ma_cay: str
    nhu_cau: str
    lot: str
    ngay_xuat: date
    vi_tri: str | None
    issue_status: str
    ten_art: str | None


def _ascii_fold(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _is_valid_pending_return_ma_cay(value: str | None) -> bool:
    folded = _ascii_fold(value)
    if not folded:
        return False
    return re.fullmatch(r"\d+\s*cay", folded) is None


def _pending_return_base_query(db: Session):
    sub = select(ReturnEvent.issue_line_id)
    rl_latest = (
        db.query(
            ReceiptLine.ma_cay.label("ma_cay"),
            func.max(ReceiptLine.id).label("rid"),
        )
        .group_by(ReceiptLine.ma_cay)
        .subquery()
    )
    rl = aliased(ReceiptLine)

    nhu_cau_expr = func.coalesce(
        func.nullif(Issue.nhu_cau, "UNKNOWN"),
        func.nullif(rl.nhu_cau, "UNKNOWN"),
        func.nullif(LocationAssignment.nhu_cau, "UNKNOWN"),
        func.nullif(StockCheck.nhu_cau, "UNKNOWN"),
        "UNKNOWN",
    )
    lot_expr = func.coalesce(
        func.nullif(Issue.lot, "UNKNOWN"),
        func.nullif(rl.lot, "UNKNOWN"),
        func.nullif(LocationAssignment.lot, "UNKNOWN"),
        func.nullif(StockCheck.lot, "UNKNOWN"),
        "UNKNOWN",
    )
    ten_art_expr = func.coalesce(
        rl.raw_data.op("->>")("Tên Art"),
        rl.raw_data.op("->>")("TÃªn Art"),
        rl.art,
        "",
    )

    query = (
        db.query(
            IssueLine.id.label("issue_line_id"),
            IssueLine.ma_cay.label("ma_cay"),
            nhu_cau_expr.label("nhu_cau"),
            lot_expr.label("lot"),
            Issue.ngay_xuat.label("ngay_xuat"),
            IssueLine.vi_tri.label("vi_tri"),
            Issue.status.label("issue_status"),
            ten_art_expr.label("ten_art"),
        )
        .join(Issue, Issue.id == IssueLine.issue_id)
        .outerjoin(rl_latest, rl_latest.c.ma_cay == IssueLine.ma_cay)
        .outerjoin(rl, rl.id == rl_latest.c.rid)
        .outerjoin(LocationAssignment, LocationAssignment.ma_cay == IssueLine.ma_cay)
        .outerjoin(StockCheck, StockCheck.ma_cay == IssueLine.ma_cay)
        .filter(~IssueLine.id.in_(sub))
    )
    return query, nhu_cau_expr, lot_expr, ten_art_expr


def list_return_candidates(
    db: Session,
    *,
    nhu_cau: str | None = None,
    lot: str | None = None,
    ten_art: str | None = None,
    limit: int = 300,
) -> list[ReturnCandidateRow]:
    """
    Rolls that have been issued but not yet returned (1 return per issue_line).
    """
    q, nhu_cau_expr, lot_expr, ten_art_expr = _pending_return_base_query(db)

    if nhu_cau:
        q = q.filter(nhu_cau_expr.ilike(f"%{nhu_cau}%"))
    if lot:
        q = q.filter(lot_expr.ilike(f"%{lot}%"))
    if ten_art:
        q = q.filter(func.coalesce(ten_art_expr, "").ilike(f"%{ten_art}%"))

    rows = q.order_by(Issue.ngay_xuat.desc(), IssueLine.id.desc()).all()
    return [
        ReturnCandidateRow(
            issue_line_id=row.issue_line_id,
            ma_cay=row.ma_cay,
            nhu_cau=row.nhu_cau,
            lot=row.lot,
            ngay_xuat=row.ngay_xuat,
            vi_tri=row.vi_tri,
            issue_status=row.issue_status,
            ten_art=row.ten_art,
        )
        for row in rows
        if _is_valid_pending_return_ma_cay(row.ma_cay)
    ][:limit]


def list_pending_return_nhu_cau_options(db: Session, *, limit: int = 2000) -> list[str]:
    q, nhu_cau_expr, _, _ = _pending_return_base_query(db)
    rows = (
        q.with_entities(nhu_cau_expr)
        .filter(nhu_cau_expr.isnot(None))
        .distinct()
        .order_by(nhu_cau_expr)
        .limit(limit)
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]


def list_pending_return_lot_options(db: Session, *, limit: int = 2000) -> list[str]:
    q, _, lot_expr, _ = _pending_return_base_query(db)
    rows = (
        q.with_entities(lot_expr)
        .filter(lot_expr.isnot(None))
        .distinct()
        .order_by(lot_expr)
        .limit(limit)
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]


def create_return(
    db: Session,
    *,
    issue_line_id: int,
    ma_cay: str,
    ngay_tai_nhap: date,
    yds_du: float | None,
    status: str,
    nhu_cau_moi: str | None,
    lot_moi: str | None,
    vi_tri_moi: str | None,
    note: str | None,
) -> int:
    ev = ReturnEvent(
        issue_line_id=issue_line_id,
        ma_cay=ma_cay,
        ngay_tai_nhap=ngay_tai_nhap,
        yds_du=yds_du,
        status=status,
        nhu_cau_moi=nhu_cau_moi,
        lot_moi=lot_moi,
        vi_tri_moi=vi_tri_moi,
        note=note,
    )
    db.add(ev)
    db.flush()

    assign = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == ma_cay).first()
    if assign:
        if status == "Tái nhập kho":
            if nhu_cau_moi:
                assign.nhu_cau = nhu_cau_moi
            if lot_moi:
                assign.lot = lot_moi
            if vi_tri_moi:
                assign.vi_tri = vi_tri_moi
            assign.trang_thai = "Đang lưu"
        elif status == "Trả Mẹ Nhu":
            assign.trang_thai = "Trả Mẹ Nhu"
        db.add(assign)

    return ev.id


def list_return_history(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int = 200,
) -> list[ReturnEvent]:
    q = db.query(ReturnEvent).order_by(ReturnEvent.ngay_tai_nhap.desc(), ReturnEvent.id.desc())
    if date_from:
        q = q.filter(ReturnEvent.ngay_tai_nhap >= date_from)
    if date_to:
        q = q.filter(ReturnEvent.ngay_tai_nhap <= date_to)
    return q.limit(limit).all()
