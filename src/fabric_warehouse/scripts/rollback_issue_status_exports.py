from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.session import SessionLocal


ACTIVE_STATUS = "Đang lưu"
DEFAULT_STATUS = "Xuất do kiểm pallet thiếu thực tế"


@dataclass(frozen=True)
class RollbackRow:
    issue_id: int
    issue_line_id: int
    ma_cay: str
    restore_vi_tri: str | None
    nhu_cau: str
    lot: str
    ngay_xuat: date


def _parse_date(raw: str | None, *, field_name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception as exc:
        raise SystemExit(f"{field_name} must be YYYY-MM-DD, got: {raw}") from exc


def _collect_rows(
    db: Session,
    *,
    status: str,
    issue_date: date | None,
    issue_ids: set[int] | None,
    ma_cays: set[str] | None,
) -> list[RollbackRow]:
    q = (
        db.query(Issue, IssueLine)
        .join(IssueLine, IssueLine.issue_id == Issue.id)
        .filter(Issue.status == status)
    )
    if issue_date:
        q = q.filter(Issue.ngay_xuat == issue_date)
    if issue_ids:
        q = q.filter(Issue.id.in_(issue_ids))
    if ma_cays:
        q = q.filter(IssueLine.ma_cay.in_(ma_cays))

    rows: list[RollbackRow] = []
    for issue, line in q.order_by(Issue.id.asc(), IssueLine.id.asc()).all():
        rows.append(
            RollbackRow(
                issue_id=issue.id,
                issue_line_id=line.id,
                ma_cay=line.ma_cay,
                restore_vi_tri=line.vi_tri,
                nhu_cau=issue.nhu_cau,
                lot=issue.lot,
                ngay_xuat=issue.ngay_xuat,
            )
        )
    return rows


def _print_plan(rows: list[RollbackRow]) -> None:
    if not rows:
        print("No issue lines found to rollback.")
        return

    issue_ids = sorted({row.issue_id for row in rows})
    print(f"Found {len(issue_ids)} issue documents / {len(rows)} roll lines to rollback.")
    grouped: dict[int, list[RollbackRow]] = {}
    for row in rows:
        grouped.setdefault(row.issue_id, []).append(row)

    for issue_id in issue_ids[:30]:
        items = grouped[issue_id]
        first = items[0]
        print(f"- issue #{issue_id} | {first.ngay_xuat} | {first.nhu_cau} / {first.lot}: {len(items)} rolls")
        for item in items[:8]:
            print(f"  {item.ma_cay} -> {item.restore_vi_tri or '-'}")
        if len(items) > 8:
            print(f"  ... +{len(items) - 8} more")
    if len(issue_ids) > 30:
        print(f"... +{len(issue_ids) - 30} more issue documents")


def rollback_exports(
    db: Session,
    *,
    status: str,
    issue_date: date | None,
    issue_ids: set[int] | None,
    ma_cays: set[str] | None,
    execute: bool,
) -> dict[str, int]:
    rows = _collect_rows(db, status=status, issue_date=issue_date, issue_ids=issue_ids, ma_cays=ma_cays)
    _print_plan(rows)
    if not rows or not execute:
        return {"assignments_restored": 0, "issue_lines_deleted": 0, "issues_deleted": 0}

    restore_by_ma: dict[str, str | None] = {}
    for row in rows:
        restore_by_ma[row.ma_cay] = row.restore_vi_tri

    assignments = db.query(LocationAssignment).filter(LocationAssignment.ma_cay.in_(list(restore_by_ma))).all()
    restored = 0
    for assignment in assignments:
        assignment.trang_thai = ACTIVE_STATUS
        restore_vi_tri = restore_by_ma.get(assignment.ma_cay)
        if restore_vi_tri:
            assignment.vi_tri = restore_vi_tri
        db.add(assignment)
        restored += 1

    line_ids = [row.issue_line_id for row in rows]
    issue_ids_to_check = sorted({row.issue_id for row in rows})

    deleted_lines = int(
        db.query(IssueLine)
        .filter(IssueLine.id.in_(line_ids))
        .delete(synchronize_session=False)
    )

    remaining_counts = dict(
        db.query(IssueLine.issue_id, func.count(IssueLine.id))
        .filter(IssueLine.issue_id.in_(issue_ids_to_check))
        .group_by(IssueLine.issue_id)
        .all()
    )
    empty_issue_ids = [issue_id for issue_id in issue_ids_to_check if int(remaining_counts.get(issue_id, 0)) == 0]
    deleted_issues = 0
    if empty_issue_ids:
        deleted_issues = int(
            db.query(Issue)
            .filter(Issue.id.in_(empty_issue_ids))
            .delete(synchronize_session=False)
        )

    return {
        "assignments_restored": restored,
        "issue_lines_deleted": deleted_lines,
        "issues_deleted": deleted_issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rollback export issues by status, restoring rolls to the issue line location."
    )
    parser.add_argument("--status", default=DEFAULT_STATUS, help="Issue.status to rollback.")
    parser.add_argument("--issue-date", help="Optional Issue.ngay_xuat filter, YYYY-MM-DD.")
    parser.add_argument("--issue-id", action="append", type=int, help="Optional issue id. Can be repeated.")
    parser.add_argument("--ma-cay", action="append", help="Optional roll code. Can be repeated.")
    parser.add_argument("--execute", action="store_true", help="Write changes. Omit for dry-run.")
    args = parser.parse_args()

    issue_date = _parse_date(args.issue_date, field_name="--issue-date")
    issue_ids = set(args.issue_id or []) or None
    ma_cays = {str(v or "").strip() for v in (args.ma_cay or []) if str(v or "").strip()} or None

    db = SessionLocal()
    try:
        result = rollback_exports(
            db,
            status=args.status,
            issue_date=issue_date,
            issue_ids=issue_ids,
            ma_cays=ma_cays,
            execute=bool(args.execute),
        )
        if args.execute:
            db.commit()
            print(
                "Committed rollback: "
                f"assignments_restored={result['assignments_restored']}, "
                f"issue_lines_deleted={result['issue_lines_deleted']}, "
                f"issues_deleted={result['issues_deleted']}"
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
