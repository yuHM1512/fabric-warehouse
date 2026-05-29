from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.pallet_stock_check import PalletStockCheck
from fabric_warehouse.db.models.pallet_stock_check_session import PalletStockCheckSession
from fabric_warehouse.db.session import SessionLocal
from fabric_warehouse.wms.stock_check_service import build_pallet_audit_day_report


ACTIVE_STATUS = "Đang lưu"
AUTO_EXPORT_NOTE_PREFIX = "Auto export unresolved pallet audit rolls."


@dataclass(frozen=True)
class ClearedRoll:
    ma_cay: str
    target_vi_tri: str
    source: str


@dataclass(frozen=True)
class RollbackLine:
    issue_id: int
    issue_line_id: int
    ma_cay: str
    issue_vi_tri: str | None
    target_vi_tri: str
    source: str


def _parse_date(raw: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except Exception as exc:
        raise SystemExit(f"{field_name} must be YYYY-MM-DD, got: {raw}") from exc


def _collect_cleared_rolls(db: Session, *, report_day: date) -> dict[str, ClearedRoll]:
    report = build_pallet_audit_day_report(db, day=report_day)
    cleared: dict[str, ClearedRoll] = {}

    # These are the old "missing in pallet A" rows that were found as extra in another checked pallet.
    for row in report.rows:
        for item in row.resolved_missing:
            ma_cay = (item.ma_cay or "").strip()
            target = (item.found_vi_tri or "").strip()
            if ma_cay and target:
                cleared[ma_cay] = ClearedRoll(ma_cay=ma_cay, target_vi_tri=target, source="resolved_missing")

    # Also include direct extra rows from the audit day. This covers the case where the issue line was exported
    # before the report logic was re-run, but the audit session already proved the roll exists physically.
    sessions = (
        db.query(PalletStockCheckSession)
        .filter(func.date(PalletStockCheckSession.created_at) == report_day)
        .all()
    )
    if sessions:
        checks = (
            db.query(PalletStockCheck)
            .filter(PalletStockCheck.session_id.in_([s.id for s in sessions]))
            .filter(PalletStockCheck.expected_in_system.is_(False))
            .filter(PalletStockCheck.present_actual.is_(True))
            .order_by(PalletStockCheck.session_id.asc(), PalletStockCheck.id.asc())
            .all()
        )
        for check in checks:
            ma_cay = (check.ma_cay or "").strip()
            target = (check.vi_tri or "").strip()
            if ma_cay and target:
                cleared[ma_cay] = ClearedRoll(ma_cay=ma_cay, target_vi_tri=target, source="audit_extra")

    return cleared


def _latest_audit_extra_target(db: Session, *, ma_cay: str, fallback: str) -> str:
    log = (
        db.query(LocationTransferLog)
        .filter(LocationTransferLog.ma_cay == ma_cay)
        .filter(LocationTransferLog.note == "pallet_stock_check_extra")
        .order_by(LocationTransferLog.created_at.desc(), LocationTransferLog.id.desc())
        .first()
    )
    if log and log.to_vi_tri:
        return log.to_vi_tri
    return fallback


def _collect_rollback_lines(
    db: Session,
    *,
    report_day: date,
    cleared: dict[str, ClearedRoll],
    ma_cays: set[str] | None,
) -> list[RollbackLine]:
    if not cleared:
        return []

    candidate_ma_cays = set(cleared)
    if ma_cays is not None:
        candidate_ma_cays &= ma_cays
    if not candidate_ma_cays:
        return []

    q = (
        db.query(Issue, IssueLine)
        .join(IssueLine, IssueLine.issue_id == Issue.id)
        .filter(IssueLine.ma_cay.in_(candidate_ma_cays))
        .filter(Issue.note.ilike(f"{AUTO_EXPORT_NOTE_PREFIX}%"))
        .filter(Issue.note.ilike(f"%report_day={report_day.isoformat()}%"))
        .order_by(Issue.id.asc(), IssueLine.id.asc())
    )

    rows: list[RollbackLine] = []
    for issue, line in q.all():
        cleared_roll = cleared.get(line.ma_cay)
        if not cleared_roll:
            continue
        target = _latest_audit_extra_target(db, ma_cay=line.ma_cay, fallback=cleared_roll.target_vi_tri)
        rows.append(
            RollbackLine(
                issue_id=issue.id,
                issue_line_id=line.id,
                ma_cay=line.ma_cay,
                issue_vi_tri=line.vi_tri,
                target_vi_tri=target,
                source=cleared_roll.source,
            )
        )
    return rows


def _print_plan(lines: list[RollbackLine]) -> None:
    if not lines:
        print("No cleared audit export lines found to rollback.")
        return

    print(f"Found {len(lines)} cleared audit export lines to rollback:")
    for line in lines:
        print(
            f"- issue #{line.issue_id} line #{line.issue_line_id}: {line.ma_cay}"
            f" | issue_vi_tri={line.issue_vi_tri or '-'}"
            f" | restore_vi_tri={line.target_vi_tri}"
            f" | source={line.source}"
        )


def rollback_cleared_exports(
    db: Session,
    *,
    report_day: date,
    ma_cays: set[str] | None,
    execute: bool,
) -> dict[str, int]:
    cleared = _collect_cleared_rolls(db, report_day=report_day)
    lines = _collect_rollback_lines(db, report_day=report_day, cleared=cleared, ma_cays=ma_cays)
    _print_plan(lines)
    if not execute or not lines:
        return {"issue_lines_deleted": 0, "issues_deleted": 0, "assignments_restored": 0}

    issue_ids = sorted({line.issue_id for line in lines})
    line_ids = [line.issue_line_id for line in lines]
    restore_by_ma = {line.ma_cay: line.target_vi_tri for line in lines}

    assignments = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.ma_cay.in_(list(restore_by_ma)))
        .all()
    )
    restored = 0
    for assignment in assignments:
        target = restore_by_ma.get(assignment.ma_cay)
        if not target:
            continue
        assignment.trang_thai = ACTIVE_STATUS
        assignment.vi_tri = target
        db.add(assignment)
        restored += 1

    deleted_lines = int(
        db.query(IssueLine)
        .filter(IssueLine.id.in_(line_ids))
        .delete(synchronize_session=False)
    )

    remaining_counts = dict(
        db.query(IssueLine.issue_id, func.count(IssueLine.id))
        .filter(IssueLine.issue_id.in_(issue_ids))
        .group_by(IssueLine.issue_id)
        .all()
    )
    empty_issue_ids = [issue_id for issue_id in issue_ids if int(remaining_counts.get(issue_id, 0)) == 0]
    deleted_issues = 0
    if empty_issue_ids:
        deleted_issues = int(
            db.query(Issue)
            .filter(Issue.id.in_(empty_issue_ids))
            .delete(synchronize_session=False)
        )

    return {
        "issue_lines_deleted": deleted_lines,
        "issues_deleted": deleted_issues,
        "assignments_restored": restored,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rollback auto exports for pallet audit rolls that were later cleared by audit extra rows."
    )
    parser.add_argument("--report-day", required=True, help="Audit report day used by the old export script, YYYY-MM-DD.")
    parser.add_argument("--ma-cay", action="append", help="Optional roll code to rollback. Can be repeated.")
    parser.add_argument("--execute", action="store_true", help="Write changes. Omit for dry-run.")
    args = parser.parse_args()

    report_day = _parse_date(args.report_day, field_name="--report-day")
    ma_cays = {str(v or "").strip() for v in (args.ma_cay or []) if str(v or "").strip()} or None

    db = SessionLocal()
    try:
        result = rollback_cleared_exports(
            db,
            report_day=report_day,
            ma_cays=ma_cays,
            execute=bool(args.execute),
        )
        if args.execute:
            db.commit()
            print(
                "Committed rollback: "
                f"issue_lines_deleted={result['issue_lines_deleted']}, "
                f"issues_deleted={result['issues_deleted']}, "
                f"assignments_restored={result['assignments_restored']}"
            )
        else:
            db.rollback()
            print("Dry-run only. Re-run with --execute to write changes.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
