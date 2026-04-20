from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.stock_check import StockCheck


@dataclass(frozen=True)
class IssueCandidateRow:
    ma_cay: str
    vi_tri: str | None
    actual_yards: float | None
    trang_thai: str | None


def list_issue_nhu_cau_options(db: Session) -> list[str]:
    rows = (
        db.query(LocationAssignment.nhu_cau)
        .filter(LocationAssignment.trang_thai == "Đang lưu")
        .distinct()
        .order_by(LocationAssignment.nhu_cau.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_issue_lot_options(db: Session, *, nhu_cau: str) -> list[str]:
    rows = (
        db.query(LocationAssignment.lot)
        .filter(LocationAssignment.nhu_cau == nhu_cau)
        .filter(LocationAssignment.trang_thai == "Đang lưu")
        .distinct()
        .order_by(LocationAssignment.lot.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_issue_candidates(db: Session, *, nhu_cau: str, lot: str) -> list[IssueCandidateRow]:
    assigns = (
        db.query(LocationAssignment.ma_cay, LocationAssignment.vi_tri, LocationAssignment.trang_thai)
        .filter(LocationAssignment.nhu_cau == nhu_cau)
        .filter(LocationAssignment.lot == lot)
        .filter(LocationAssignment.trang_thai == "Đang lưu")
        .order_by(LocationAssignment.vi_tri.asc(), LocationAssignment.ma_cay.asc())
        .all()
    )
    actual = (
        db.query(StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.nhu_cau == nhu_cau)
        .filter(StockCheck.lot == lot)
        .all()
    )
    actual_by_ma = {m: (float(y) if y is not None else None) for m, y in actual}

    return [
        IssueCandidateRow(ma_cay=ma, vi_tri=vt, actual_yards=actual_by_ma.get(ma), trang_thai=st)
        for ma, vt, st in assigns
    ]


def create_issue(
    db: Session,
    *,
    nhu_cau: str,
    lot: str,
    ngay_xuat: date,
    status: str,
    note: str | None,
    ma_cays: list[str],
) -> int:
    issue = Issue(nhu_cau=nhu_cau, lot=lot, ngay_xuat=ngay_xuat, status=status, note=note)
    db.add(issue)
    db.flush()

    assigns = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.ma_cay.in_(ma_cays))
        .filter(LocationAssignment.trang_thai == "Đang lưu")
        .all()
    )
    assign_by_ma = {a.ma_cay: a for a in assigns}

    checks = (
        db.query(StockCheck.ma_cay, StockCheck.actual_yards)
        .filter(StockCheck.nhu_cau == nhu_cau)
        .filter(StockCheck.lot == lot)
        .filter(StockCheck.ma_cay.in_(ma_cays))
        .all()
    )
    qty_by_ma = {m: (float(y) if y is not None else None) for m, y in checks}

    lines: list[IssueLine] = []
    for ma in ma_cays:
        a = assign_by_ma.get(ma)
        lines.append(
            IssueLine(
                issue_id=issue.id,
                ma_cay=ma,
                so_luong_xuat=qty_by_ma.get(ma),
                vi_tri=a.vi_tri if a else None,
            )
        )

    db.add_all(lines)
    db.flush()

    # Update location status
    for a in assigns:
        a.trang_thai = "Đã xuất"
        db.add(a)

    return issue.id


def list_issue_history(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int = 200,
) -> list[Issue]:
    q = db.query(Issue).order_by(Issue.ngay_xuat.desc(), Issue.id.desc())
    if date_from:
        q = q.filter(Issue.ngay_xuat >= date_from)
    if date_to:
        q = q.filter(Issue.ngay_xuat <= date_to)
    return q.limit(limit).all()


def count_issue_lines(db: Session, *, issue_ids: list[int]) -> dict[int, int]:
    if not issue_ids:
        return {}
    rows = (
        db.query(IssueLine.issue_id, func.count(IssueLine.id))
        .filter(IssueLine.issue_id.in_(issue_ids))
        .group_by(IssueLine.issue_id)
        .all()
    )
    return {iid: int(c) for iid, c in rows}

