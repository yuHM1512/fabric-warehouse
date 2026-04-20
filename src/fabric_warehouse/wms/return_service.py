from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
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


def list_return_candidates(db: Session, *, limit: int = 300) -> list[ReturnCandidateRow]:
    """
    Rolls that have been issued but not yet returned (1 return per issue_line).
    """
    sub = db.query(ReturnEvent.issue_line_id).subquery()
    rows = (
        db.query(
            IssueLine.id,
            IssueLine.ma_cay,
            Issue.nhu_cau,
            Issue.lot,
            Issue.ngay_xuat,
            IssueLine.vi_tri,
            Issue.status,
        )
        .join(Issue, Issue.id == IssueLine.issue_id)
        .filter(~IssueLine.id.in_(sub))
        .order_by(Issue.ngay_xuat.desc(), IssueLine.id.desc())
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
        )
        for iid, ma, nc, lt, nx, vt, st in rows
    ]


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

