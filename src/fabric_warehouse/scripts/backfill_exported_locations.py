from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from fabric_warehouse.config import settings
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EXPORTED_STATUS = "Đã xuất"


@dataclass(frozen=True)
class ExportedRollGap:
    ma_cay: str
    nhu_cau: str
    lot: str
    issue_line_id: int
    issue_id: int
    issue_vi_tri: str | None
    source_at: datetime
    location_assignment_id: int | None
    assignment_vi_tri: str | None
    assignment_status: str | None
    assignment_assigned_at: datetime | None
    assignment_updated_at: datetime | None
    has_initial_log: bool

    @property
    def needs_assignment_backfill(self) -> bool:
        return bool(self.issue_vi_tri) and not (self.assignment_vi_tri or "").strip()

    @property
    def needs_log_backfill(self) -> bool:
        return bool(self.issue_vi_tri) and not self.has_initial_log

    @property
    def missing_position_everywhere(self) -> bool:
        return not (self.issue_vi_tri or "").strip() and not (self.assignment_vi_tri or "").strip()


def _session_factory(database_url: str | None = None):
    engine = create_engine(database_url or settings.database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _source_at(created_at: datetime | None, ngay_xuat) -> datetime:
    if created_at is not None:
        return created_at
    return datetime.combine(ngay_xuat, time(0, 0), tzinfo=VN_TZ)


def collect_exported_roll_gaps(db: Session, *, ma_cays: list[str] | None = None) -> list[ExportedRollGap]:
    sql = """
    with latest_issue as (
      select distinct on (il.ma_cay)
        il.ma_cay,
        il.id as issue_line_id,
        il.issue_id,
        il.vi_tri as issue_vi_tri,
        i.nhu_cau,
        i.lot,
        i.ngay_xuat,
        i.created_at
      from issue_lines il
      join issues i on i.id = il.issue_id
      left join return_events re on re.issue_line_id = il.id
      where re.id is null
      order by il.ma_cay, i.ngay_xuat desc, i.id desc, il.id desc
    ),
    init_logs as (
      select distinct ma_cay, to_vi_tri
      from location_transfer_logs
      where from_vi_tri is null
    )
    select
      li.ma_cay,
      li.nhu_cau,
      li.lot,
      li.issue_line_id,
      li.issue_id,
      li.issue_vi_tri,
      li.ngay_xuat,
      li.created_at,
      la.id as location_assignment_id,
      la.vi_tri as assignment_vi_tri,
      la.trang_thai as assignment_status,
      la.assigned_at as assignment_assigned_at,
      la.updated_at as assignment_updated_at,
      case when il.ma_cay is not null then true else false end as has_initial_log
    from latest_issue li
    left join location_assignments la on la.ma_cay = li.ma_cay
    left join init_logs il on il.ma_cay = li.ma_cay and il.to_vi_tri = li.issue_vi_tri
    where (:ma_cay_filter_off = 1 or li.ma_cay = any(:ma_cays))
      and (
        li.issue_vi_tri is null
        or btrim(li.issue_vi_tri) = ''
        or la.id is null
        or la.vi_tri is null
        or btrim(la.vi_tri) = ''
        or il.ma_cay is null
      )
    order by li.ngay_xuat desc, li.issue_id desc, li.issue_line_id desc
    """
    params = {
        "ma_cay_filter_off": 0 if ma_cays else 1,
        "ma_cays": ma_cays or [],
    }
    rows = db.execute(text(sql), params).mappings().all()
    return [
        ExportedRollGap(
            ma_cay=row["ma_cay"],
            nhu_cau=row["nhu_cau"],
            lot=row["lot"],
            issue_line_id=row["issue_line_id"],
            issue_id=row["issue_id"],
            issue_vi_tri=row["issue_vi_tri"],
            source_at=_source_at(row["created_at"], row["ngay_xuat"]),
            location_assignment_id=row["location_assignment_id"],
            assignment_vi_tri=row["assignment_vi_tri"],
            assignment_status=row["assignment_status"],
            assignment_assigned_at=row["assignment_assigned_at"],
            assignment_updated_at=row["assignment_updated_at"],
            has_initial_log=bool(row["has_initial_log"]),
        )
        for row in rows
    ]


def print_report(gaps: list[ExportedRollGap]) -> None:
    if not gaps:
        print("No exported ma_cay missing location data.")
        return

    print(f"Found {len(gaps)} exported ma_cay with location gaps:")
    for gap in gaps[:200]:
        flags: list[str] = []
        if gap.missing_position_everywhere:
            flags.append("missing_position_everywhere")
        if gap.needs_assignment_backfill:
            flags.append("needs_assignment_backfill")
        if gap.needs_log_backfill:
            flags.append("needs_log_backfill")
        print(
            f"- {gap.ma_cay} | {gap.nhu_cau}/{gap.lot} | issue #{gap.issue_id}/{gap.issue_line_id}"
            f" | issue_vi_tri={gap.issue_vi_tri or '-'} | assignment={gap.assignment_vi_tri or '-'}"
            f" | flags={','.join(flags) or 'none'}"
        )
    if len(gaps) > 200:
        print(f"... {len(gaps) - 200} more rows omitted.")


def apply_backfill(db: Session, gaps: list[ExportedRollGap]) -> dict[str, int]:
    inserted_assignments = 0
    updated_assignments = 0
    inserted_logs = 0

    for gap in gaps:
        if gap.missing_position_everywhere:
            continue

        if gap.needs_assignment_backfill:
            if gap.location_assignment_id is None:
                db.execute(
                    text(
                        """
                        insert into location_assignments
                          (ma_cay, nhu_cau, lot, anh_mau, vi_tri, trang_thai, assigned_at, updated_at)
                        values
                          (:ma_cay, :nhu_cau, :lot, null, :vi_tri, :trang_thai, :assigned_at, :updated_at)
                        """
                    ),
                    {
                        "ma_cay": gap.ma_cay,
                        "nhu_cau": gap.nhu_cau,
                        "lot": gap.lot,
                        "vi_tri": gap.issue_vi_tri,
                        "trang_thai": gap.assignment_status or EXPORTED_STATUS,
                        "assigned_at": gap.source_at,
                        "updated_at": gap.source_at,
                    },
                )
                inserted_assignments += 1
            else:
                db.execute(
                    text(
                        """
                        update location_assignments
                        set vi_tri = :vi_tri,
                            nhu_cau = coalesce(nhu_cau, :nhu_cau),
                            lot = coalesce(lot, :lot),
                            trang_thai = coalesce(trang_thai, :trang_thai)
                        where id = :id
                        """
                    ),
                    {
                        "id": gap.location_assignment_id,
                        "vi_tri": gap.issue_vi_tri,
                        "nhu_cau": gap.nhu_cau,
                        "lot": gap.lot,
                        "trang_thai": EXPORTED_STATUS,
                    },
                )
                updated_assignments += 1

        if gap.needs_log_backfill:
            db.add(
                LocationTransferLog(
                    ma_cay=gap.ma_cay,
                    nhu_cau=gap.nhu_cau,
                    lot=gap.lot,
                    from_vi_tri=None,
                    to_vi_tri=gap.issue_vi_tri or "",
                    note="backfill_exported_location",
                    created_at=gap.assignment_assigned_at or gap.source_at,
                )
            )
            inserted_logs += 1

    return {
        "inserted_location_assignments": inserted_assignments,
        "updated_location_assignments": updated_assignments,
        "inserted_location_transfer_logs": inserted_logs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_exported_locations",
        description="Backfill historical location data for currently exported rolls without changing updated_at.",
    )
    parser.add_argument("--database-url", default="", help="Optional SQLAlchemy database URL override.")
    parser.add_argument("--ma-cay", nargs="*", default=[], help="Only inspect specific ma_cay values.")
    parser.add_argument("--apply", action="store_true", help="Apply the backfill. Default is dry-run.")
    args = parser.parse_args(argv)

    SessionLocal = _session_factory(args.database_url.strip() or None)
    db = SessionLocal()
    try:
        gaps = collect_exported_roll_gaps(db, ma_cays=[m.strip() for m in args.ma_cay if m.strip()] or None)
        print_report(gaps)
        if not args.apply:
            print("Dry-run only. Re-run with --apply to commit changes.")
            db.rollback()
            return 0

        stats = apply_backfill(db, gaps)
        db.commit()
        print("Applied backfill:")
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
