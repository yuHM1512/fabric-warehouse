from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from fabric_warehouse.config import settings
from fabric_warehouse.db.models.demand_transfer_log import DemandTransferLog
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.return_event import ReturnEvent

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EXPORTED_STATUS = "Đã xuất"


@dataclass(frozen=True)
class IssueOccurrence:
    issue_id: int
    issue_line_id: int
    ma_cay: str
    nhu_cau: str
    lot: str
    vi_tri: str | None
    ngay_xuat: datetime


@dataclass(frozen=True)
class InvalidWindow:
    start: datetime
    end: datetime | None
    blocker_issue_line_id: int


@dataclass
class CleanupPlan:
    ma_cay: str
    kept_issue_line_ids: list[int]
    duplicate_issue_line_ids: list[int]
    duplicate_issue_ids: list[int]
    return_event_ids_to_delete: list[int]
    location_log_ids_to_delete: list[int]
    demand_log_ids_to_delete: list[int]
    restore_assignment_from_issue_line_id: int | None
    restore_assignment_to_vi_tri: str | None
    restore_assignment_to_nhu_cau: str | None
    restore_assignment_to_lot: str | None


def _session_factory(database_url: str | None = None):
    engine = create_engine(database_url or settings.database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _issue_at(issue: Issue) -> datetime:
    if issue.created_at:
        return issue.created_at
    return datetime.combine(issue.ngay_xuat, time(0, 0), tzinfo=VN_TZ)


def _return_at(ret: ReturnEvent) -> datetime:
    if ret.ngay_tai_nhap:
        return datetime.combine(ret.ngay_tai_nhap, time(0, 0), tzinfo=VN_TZ)
    return ret.created_at


def _windows_for_duplicates(
    occurrences: list[IssueOccurrence],
    return_at_by_issue_line: dict[int, datetime],
) -> tuple[list[int], list[int], list[InvalidWindow]]:
    kept_ids: list[int] = []
    duplicate_ids: list[int] = []
    windows: list[InvalidWindow] = []
    active_keep: IssueOccurrence | None = None

    for occ in occurrences:
        if active_keep is not None:
            keep_return_at = return_at_by_issue_line.get(active_keep.issue_line_id)
            if keep_return_at and keep_return_at <= occ.ngay_xuat:
                active_keep = None

        if active_keep is None:
            kept_ids.append(occ.issue_line_id)
            active_keep = occ
            continue

        duplicate_ids.append(occ.issue_line_id)
        blocker_return_at = return_at_by_issue_line.get(active_keep.issue_line_id)
        window = InvalidWindow(
            start=active_keep.ngay_xuat,
            end=blocker_return_at,
            blocker_issue_line_id=active_keep.issue_line_id,
        )
        if window not in windows:
            windows.append(window)

    return kept_ids, duplicate_ids, windows


def _in_window(at: datetime | None, windows: Iterable[InvalidWindow]) -> bool:
    if at is None:
        return False
    for window in windows:
        if at < window.start:
            continue
        if window.end is not None and at >= window.end:
            continue
        return True
    return False


def build_cleanup_plan(db: Session, *, ma_cays: list[str] | None = None) -> list[CleanupPlan]:
    dup_query = (
        db.query(IssueLine.ma_cay)
        .group_by(IssueLine.ma_cay)
        .having(func.count(IssueLine.id) > 1)
        .order_by(IssueLine.ma_cay.asc())
    )
    if ma_cays:
        dup_query = dup_query.filter(IssueLine.ma_cay.in_(ma_cays))
    duplicate_ma_cays = [row[0] for row in dup_query.all() if row and row[0]]

    plans: list[CleanupPlan] = []
    for ma_cay in duplicate_ma_cays:
        rows = (
            db.query(IssueLine, Issue)
            .join(Issue, Issue.id == IssueLine.issue_id)
            .filter(IssueLine.ma_cay == ma_cay)
            .order_by(Issue.ngay_xuat.asc(), Issue.created_at.asc(), Issue.id.asc(), IssueLine.id.asc())
            .all()
        )
        occurrences = [
            IssueOccurrence(
                issue_id=issue.id,
                issue_line_id=line.id,
                ma_cay=ma_cay,
                nhu_cau=issue.nhu_cau,
                lot=issue.lot,
                vi_tri=line.vi_tri,
                ngay_xuat=_issue_at(issue),
            )
            for line, issue in rows
        ]
        if len(occurrences) < 2:
            continue

        returns = (
            db.query(ReturnEvent)
            .filter(ReturnEvent.ma_cay == ma_cay)
            .order_by(ReturnEvent.ngay_tai_nhap.asc(), ReturnEvent.created_at.asc(), ReturnEvent.id.asc())
            .all()
        )
        return_at_by_issue_line = {ret.issue_line_id: _return_at(ret) for ret in returns}
        kept_ids, duplicate_ids, windows = _windows_for_duplicates(occurrences, return_at_by_issue_line)
        if not duplicate_ids:
            continue

        duplicate_issue_ids = sorted({occ.issue_id for occ in occurrences if occ.issue_line_id in duplicate_ids})
        return_event_ids_to_delete = [ret.id for ret in returns if ret.issue_line_id in duplicate_ids]

        location_logs = (
            db.query(LocationTransferLog)
            .filter(LocationTransferLog.ma_cay == ma_cay)
            .order_by(LocationTransferLog.created_at.asc(), LocationTransferLog.id.asc())
            .all()
        )
        demand_logs = (
            db.query(DemandTransferLog)
            .filter(DemandTransferLog.ma_cay == ma_cay)
            .order_by(DemandTransferLog.created_at.asc(), DemandTransferLog.id.asc())
            .all()
        )

        location_log_ids_to_delete = [log.id for log in location_logs if _in_window(log.created_at, windows)]
        demand_log_ids_to_delete = [log.id for log in demand_logs if _in_window(log.created_at, windows)]

        last_kept_occ = next((occ for occ in reversed(occurrences) if occ.issue_line_id in kept_ids), None)
        latest_kept_return_at = (
            return_at_by_issue_line.get(last_kept_occ.issue_line_id) if last_kept_occ is not None else None
        )
        restore_assignment = None
        restore_vi_tri = None
        restore_nhu_cau = None
        restore_lot = None
        if last_kept_occ is not None and latest_kept_return_at is None:
            restore_assignment = last_kept_occ.issue_line_id
            restore_vi_tri = last_kept_occ.vi_tri
            restore_nhu_cau = last_kept_occ.nhu_cau
            restore_lot = last_kept_occ.lot

        plans.append(
            CleanupPlan(
                ma_cay=ma_cay,
                kept_issue_line_ids=kept_ids,
                duplicate_issue_line_ids=duplicate_ids,
                duplicate_issue_ids=duplicate_issue_ids,
                return_event_ids_to_delete=return_event_ids_to_delete,
                location_log_ids_to_delete=location_log_ids_to_delete,
                demand_log_ids_to_delete=demand_log_ids_to_delete,
                restore_assignment_from_issue_line_id=restore_assignment,
                restore_assignment_to_vi_tri=restore_vi_tri,
                restore_assignment_to_nhu_cau=restore_nhu_cau,
                restore_assignment_to_lot=restore_lot,
            )
        )

    return plans


def apply_cleanup_plan(db: Session, plans: list[CleanupPlan]) -> dict[str, int]:
    deleted_issue_lines = 0
    deleted_issues = 0
    deleted_returns = 0
    deleted_location_logs = 0
    deleted_demand_logs = 0
    updated_assignments = 0

    for plan in plans:
        if plan.return_event_ids_to_delete:
            deleted_returns += int(
                db.query(ReturnEvent)
                .filter(ReturnEvent.id.in_(plan.return_event_ids_to_delete))
                .delete(synchronize_session=False)
            )

        if plan.location_log_ids_to_delete:
            deleted_location_logs += int(
                db.query(LocationTransferLog)
                .filter(LocationTransferLog.id.in_(plan.location_log_ids_to_delete))
                .delete(synchronize_session=False)
            )

        if plan.demand_log_ids_to_delete:
            deleted_demand_logs += int(
                db.query(DemandTransferLog)
                .filter(DemandTransferLog.id.in_(plan.demand_log_ids_to_delete))
                .delete(synchronize_session=False)
            )

        if plan.duplicate_issue_line_ids:
            deleted_issue_lines += int(
                db.query(IssueLine)
                .filter(IssueLine.id.in_(plan.duplicate_issue_line_ids))
                .delete(synchronize_session=False)
            )

        if plan.duplicate_issue_ids:
            orphan_issue_ids = [
                issue_id
                for (issue_id,) in db.query(Issue.id)
                .outerjoin(IssueLine, IssueLine.issue_id == Issue.id)
                .filter(Issue.id.in_(plan.duplicate_issue_ids))
                .group_by(Issue.id)
                .having(func.count(IssueLine.id) == 0)
                .all()
            ]
            if orphan_issue_ids:
                deleted_issues += int(
                    db.query(Issue).filter(Issue.id.in_(orphan_issue_ids)).delete(synchronize_session=False)
                )

        if plan.restore_assignment_from_issue_line_id is not None:
            la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == plan.ma_cay).first()
            if la:
                la.nhu_cau = plan.restore_assignment_to_nhu_cau or la.nhu_cau
                la.lot = plan.restore_assignment_to_lot or la.lot
                if plan.restore_assignment_to_vi_tri:
                    la.vi_tri = plan.restore_assignment_to_vi_tri
                la.trang_thai = EXPORTED_STATUS
                db.add(la)
                updated_assignments += 1

    return {
        "deleted_issue_lines": deleted_issue_lines,
        "deleted_issues": deleted_issues,
        "deleted_return_events": deleted_returns,
        "deleted_location_transfer_logs": deleted_location_logs,
        "deleted_demand_transfer_logs": deleted_demand_logs,
        "updated_location_assignments": updated_assignments,
    }


def _print_plan(plans: list[CleanupPlan]) -> None:
    if not plans:
        print("No duplicate issue_lines requiring cleanup.")
        return

    print(f"Found {len(plans)} ma_cay with invalid duplicate issue_lines:")
    for plan in plans:
        print(f"- ma_cay: {plan.ma_cay}")
        print(f"  keep issue_lines: {plan.kept_issue_line_ids}")
        print(f"  delete issue_lines: {plan.duplicate_issue_line_ids}")
        if plan.duplicate_issue_ids:
            print(f"  candidate issue ids to prune: {plan.duplicate_issue_ids}")
        if plan.return_event_ids_to_delete:
            print(f"  delete return_events: {plan.return_event_ids_to_delete}")
        if plan.location_log_ids_to_delete:
            print(f"  delete location_transfer_logs: {plan.location_log_ids_to_delete}")
        if plan.demand_log_ids_to_delete:
            print(f"  delete demand_transfer_logs: {plan.demand_log_ids_to_delete}")
        if plan.restore_assignment_from_issue_line_id is not None:
            print(
                "  restore location_assignment from kept issue_line "
                f"{plan.restore_assignment_from_issue_line_id}: "
                f"{plan.restore_assignment_to_nhu_cau}/{plan.restore_assignment_to_lot} @ {plan.restore_assignment_to_vi_tri}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clean_duplicate_issue_lines",
        description="Detect and clean duplicate issue_lines plus noisy post-export logs.",
    )
    parser.add_argument("--database-url", default="", help="Optional SQLAlchemy database URL override.")
    parser.add_argument("--ma-cay", nargs="*", default=[], help="Only inspect specific ma_cay values.")
    parser.add_argument("--apply", action="store_true", help="Apply destructive cleanup. Default is dry-run.")
    args = parser.parse_args(argv)

    SessionLocal = _session_factory(args.database_url.strip() or None)
    db = SessionLocal()
    try:
        plans = build_cleanup_plan(db, ma_cays=[m.strip() for m in args.ma_cay if m.strip()] or None)
        _print_plan(plans)

        if not args.apply:
            print("Dry-run only. Re-run with --apply to commit changes.")
            db.rollback()
            return 0

        stats = apply_cleanup_plan(db, plans)
        db.commit()
        print("Applied cleanup:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
