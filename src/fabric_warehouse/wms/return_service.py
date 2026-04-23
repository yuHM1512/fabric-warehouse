from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent


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
    sub = db.query(ReturnEvent.issue_line_id).subquery()
    rl_latest = (
        db.query(
            ReceiptLine.ma_cay.label("ma_cay"),
            func.max(ReceiptLine.id).label("rid"),
        )
        .group_by(ReceiptLine.ma_cay)
        .subquery()
    )
    rl = aliased(ReceiptLine)
    ten_art_expr = rl.raw_data.op("->>")("Tên Art")

    q = (
        db.query(
            IssueLine.id,
            IssueLine.ma_cay,
            Issue.nhu_cau,
            Issue.lot,
            Issue.ngay_xuat,
            IssueLine.vi_tri,
            Issue.status,
            ten_art_expr.label("ten_art"),
        )
        .join(Issue, Issue.id == IssueLine.issue_id)
        .outerjoin(rl_latest, rl_latest.c.ma_cay == IssueLine.ma_cay)
        .outerjoin(rl, rl.id == rl_latest.c.rid)
        .filter(~IssueLine.id.in_(sub))
    )

    if nhu_cau:
        q = q.filter(Issue.nhu_cau.ilike(f"%{nhu_cau}%"))
    if lot:
        q = q.filter(Issue.lot.ilike(f"%{lot}%"))
    if ten_art:
        q = q.filter(func.coalesce(ten_art_expr, "").ilike(f"%{ten_art}%"))

    rows = (
        q.order_by(Issue.ngay_xuat.desc(), IssueLine.id.desc())
        .limit(limit)
        .all()
    )
    return [
        ReturnCandidateRow(
            issue_line_id=iid,
            ma_cay=ma,
            nhu_cau=nc,
            lot=lt,
            ngay_xuat=nx,
            vi_tri=vt,
            issue_status=st,
            ten_art=ta,
        )
        for iid, ma, nc, lt, nx, vt, st, ta in rows
    ]


def list_pending_return_nhu_cau_options(db: Session, *, limit: int = 2000) -> list[str]:
    sub = db.query(ReturnEvent.issue_line_id).subquery()
    rows = (
        db.query(Issue.nhu_cau)
        .join(IssueLine, IssueLine.issue_id == Issue.id)
        .filter(~IssueLine.id.in_(sub))
        .distinct()
        .order_by(Issue.nhu_cau)
        .limit(limit)
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]


def list_pending_return_lot_options(db: Session, *, limit: int = 2000) -> list[str]:
    sub = db.query(ReturnEvent.issue_line_id).subquery()
    rows = (
        db.query(Issue.lot)
        .join(IssueLine, IssueLine.issue_id == Issue.id)
        .filter(~IssueLine.id.in_(sub))
        .distinct()
        .order_by(Issue.lot)
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

    # Update location assignment state
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
