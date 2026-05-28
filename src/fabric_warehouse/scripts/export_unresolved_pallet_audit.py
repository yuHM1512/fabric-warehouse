from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.session import SessionLocal
from fabric_warehouse.wms.issue_service import create_issue
from fabric_warehouse.wms.stock_check_service import build_pallet_audit_day_report


STORED_STATUSES = ("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")


@dataclass(frozen=True)
class ExportCandidate:
    ma_cay: str
    nhu_cau: str
    lot: str
    vi_tri: str | None
    source_pallet: str
    source_session_id: int


def _parse_date(raw: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except Exception as exc:
        raise SystemExit(f"{field_name} must be YYYY-MM-DD, got: {raw}") from exc


def _collect_candidates(db: Session, *, report_day: date) -> list[ExportCandidate]:
    report = build_pallet_audit_day_report(db, day=report_day)
    missing_ma_cays: dict[str, tuple[str, int]] = {}
    for row in report.rows:
        for missing in row.unresolved_missing:
            ma_cay = (missing.ma_cay or "").strip()
            if ma_cay and ma_cay not in missing_ma_cays:
                missing_ma_cays[ma_cay] = (row.vi_tri, row.session_id)

    if not missing_ma_cays:
        return []

    assignments = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.ma_cay.in_(list(missing_ma_cays.keys())))
        .filter(LocationAssignment.trang_thai.in_(STORED_STATUSES))
        .all()
    )
    out: list[ExportCandidate] = []
    for assignment in assignments:
        source_pallet, source_session_id = missing_ma_cays.get(assignment.ma_cay, ("", 0))
        if not assignment.nhu_cau or not assignment.lot:
            continue
        out.append(
            ExportCandidate(
                ma_cay=assignment.ma_cay,
                nhu_cau=assignment.nhu_cau,
                lot=assignment.lot,
                vi_tri=assignment.vi_tri,
                source_pallet=source_pallet,
                source_session_id=source_session_id,
            )
        )
    return sorted(out, key=lambda item: (item.nhu_cau, item.lot, item.ma_cay))


def _print_plan(candidates: list[ExportCandidate]) -> None:
    if not candidates:
        print("No unresolved stored rolls found for export.")
        return

    grouped: dict[tuple[str, str], list[ExportCandidate]] = defaultdict(list)
    for item in candidates:
        grouped[(item.nhu_cau, item.lot)].append(item)

    print(f"Found {len(candidates)} unresolved stored rolls to export:")
    for (nhu_cau, lot), items in grouped.items():
        print(f"- {nhu_cau} / {lot}: {len(items)} rolls")
        for item in items:
            print(
                f"  {item.ma_cay} | vi_tri={item.vi_tri or '-'}"
                f" | audit_pallet={item.source_pallet}"
                f" | session={item.source_session_id}"
            )


def export_unresolved(
    db: Session,
    *,
    report_day: date,
    issue_date: date,
    status: str,
    execute: bool,
) -> list[int]:
    candidates = _collect_candidates(db, report_day=report_day)
    _print_plan(candidates)
    if not execute or not candidates:
        return []

    grouped: dict[tuple[str, str], list[ExportCandidate]] = defaultdict(list)
    for item in candidates:
        grouped[(item.nhu_cau, item.lot)].append(item)

    issue_ids: list[int] = []
    for (nhu_cau, lot), items in grouped.items():
        source_sessions = sorted({str(item.source_session_id) for item in items if item.source_session_id})
        note = (
            f"Auto export unresolved pallet audit rolls. "
            f"report_day={report_day.isoformat()}; "
            f"sessions={','.join(source_sessions)}"
        )
        issue_id = create_issue(
            db,
            nhu_cau=nhu_cau,
            lot=lot,
            ngay_xuat=issue_date,
            status=status,
            note=note,
            ma_cays=[item.ma_cay for item in items],
        )
        issue_ids.append(issue_id)
    return issue_ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export rolls that remain unresolved in the pallet audit day report."
    )
    parser.add_argument("--report-day", required=True, help="Audit report day, YYYY-MM-DD.")
    parser.add_argument(
        "--issue-date",
        help="Issue date to write, YYYY-MM-DD. Defaults to --report-day.",
    )
    parser.add_argument(
        "--status",
        default="Xuất do kiểm pallet thiếu thực tế",
        help="Issue status to write.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write issues and mark location assignments as exported. Omit for dry-run.",
    )
    args = parser.parse_args()

    report_day = _parse_date(args.report_day, field_name="--report-day")
    issue_date = _parse_date(args.issue_date, field_name="--issue-date") if args.issue_date else report_day

    db = SessionLocal()
    try:
        issue_ids = export_unresolved(
            db,
            report_day=report_day,
            issue_date=issue_date,
            status=args.status,
            execute=bool(args.execute),
        )
        if args.execute:
            db.commit()
            print(f"Created {len(issue_ids)} issue documents: {issue_ids}")
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
