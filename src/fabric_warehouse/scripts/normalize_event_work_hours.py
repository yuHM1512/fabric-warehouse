from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.demand_transfer_log import DemandTransferLog
from fabric_warehouse.db.models.gon_issue import GonIssue
from fabric_warehouse.db.models.gon_stock_entry import GonStockEntry
from fabric_warehouse.db.models.gon_transfer import GonTransfer
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.pallet_stock_check import PalletStockCheck
from fabric_warehouse.db.models.pallet_stock_check_session import PalletStockCheckSession
from fabric_warehouse.db.models.return_event import ReturnEvent
from fabric_warehouse.db.session import SessionLocal


APP_TZ = ZoneInfo("Asia/Bangkok")
WORK_START = time(7, 30)
WORK_END = time(17, 0)


@dataclass(frozen=True)
class EventRef:
    entity: str
    table: str
    row_id: int
    column: str
    at: datetime
    obj: object

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.table, self.row_id, self.column)


@dataclass(frozen=True)
class PlannedChange:
    ref: EventRef
    new_at: datetime


def _parse_date(raw: str | None, *, field_name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception as exc:
        raise SystemExit(f"{field_name} must be YYYY-MM-DD, got: {raw}") from exc


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_local(dt: datetime) -> datetime:
    return _as_utc(dt).astimezone(APP_TZ)


def _from_local_like_original(local_dt: datetime, original: datetime) -> datetime:
    utc_dt = local_dt.astimezone(timezone.utc)
    if original.tzinfo is None:
        return utc_dt.replace(tzinfo=None)
    return utc_dt


def _local_bounds(from_day: date | None, to_day: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(from_day, time.min, tzinfo=APP_TZ).astimezone(timezone.utc) if from_day else None
    end = datetime.combine(to_day, time.max, tzinfo=APP_TZ).astimezone(timezone.utc) if to_day else None
    return start, end


def _filter_dt(q, column, *, from_day: date | None, to_day: date | None):
    start, end = _local_bounds(from_day, to_day)
    if start:
        q = q.filter(column >= start)
    if end:
        q = q.filter(column <= end)
    return q


def _filter_any_dt(q, columns: list[object], *, from_day: date | None, to_day: date | None):
    start, end = _local_bounds(from_day, to_day)
    clauses = []
    for column in columns:
        expr = column.isnot(None)
        if start:
            expr = expr & (column >= start)
        if end:
            expr = expr & (column <= end)
        clauses.append(expr)
    if clauses:
        q = q.filter(or_(*clauses))
    return q


def _work_window(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, WORK_START, tzinfo=APP_TZ),
        datetime.combine(day, WORK_END, tzinfo=APP_TZ),
    )


def _needs_change(local_dt: datetime) -> bool:
    current = local_dt.timetz().replace(tzinfo=None)
    return current < WORK_START or current > WORK_END


def _fit_group(events: list[EventRef]) -> list[PlannedChange]:
    if not events:
        return []

    ordered = sorted(events, key=lambda item: (_to_local(item.at), item.table, item.row_id, item.column))
    locals_old = [_to_local(item.at) for item in ordered]
    day = locals_old[0].date()
    window_start, window_end = _work_window(day)

    if all(not _needs_change(dt) for dt in locals_old):
        return []

    first = locals_old[0]
    last = locals_old[-1]
    span = last - first
    window_span = window_end - window_start

    if span <= window_span:
        shifted = locals_old
        if shifted[-1] > window_end:
            delta = shifted[-1] - window_end
            shifted = [dt - delta for dt in shifted]
        if shifted[0] < window_start:
            delta = window_start - shifted[0]
            shifted = [dt + delta for dt in shifted]
        if shifted[-1] <= window_end:
            return [
                PlannedChange(ref=ref, new_at=_from_local_like_original(new_local, ref.at))
                for ref, old_local, new_local in zip(ordered, locals_old, shifted)
                if new_local != old_local
            ]

    # If the original timeline is wider than the working window, compress it linearly.
    if len(ordered) == 1 or span.total_seconds() <= 0:
        compressed = [window_end if locals_old[0] > window_end else window_start]
    else:
        compressed = []
        for old_local in locals_old:
            ratio = (old_local - first).total_seconds() / span.total_seconds()
            compressed.append(window_start + timedelta(seconds=ratio * window_span.total_seconds()))

    return [
        PlannedChange(ref=ref, new_at=_from_local_like_original(new_local, ref.at))
        for ref, old_local, new_local in zip(ordered, locals_old, compressed)
        if new_local != old_local
    ]


def _add_event(
    out: list[EventRef],
    *,
    entity: str,
    table: str,
    row_id: int | None,
    column: str,
    at: datetime | None,
    obj: object,
) -> None:
    if row_id is None or at is None:
        return
    out.append(EventRef(entity=entity, table=table, row_id=int(row_id), column=column, at=at, obj=obj))


def _collect_fabric_events(db: Session, *, from_day: date | None, to_day: date | None) -> list[EventRef]:
    events: list[EventRef] = []

    q_assign = _filter_any_dt(
        db.query(LocationAssignment),
        [LocationAssignment.assigned_at, LocationAssignment.updated_at],
        from_day=from_day,
        to_day=to_day,
    )
    for row in q_assign.all():
        entity = f"ma_cay:{row.ma_cay}"
        _add_event(events, entity=entity, table="location_assignments", row_id=row.id, column="assigned_at", at=row.assigned_at, obj=row)
        _add_event(events, entity=entity, table="location_assignments", row_id=row.id, column="updated_at", at=row.updated_at, obj=row)

    q_loc = _filter_dt(db.query(LocationTransferLog), LocationTransferLog.created_at, from_day=from_day, to_day=to_day)
    for row in q_loc.all():
        _add_event(events, entity=f"ma_cay:{row.ma_cay}", table="location_transfer_logs", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    q_dem = _filter_dt(db.query(DemandTransferLog), DemandTransferLog.created_at, from_day=from_day, to_day=to_day)
    for row in q_dem.all():
        _add_event(events, entity=f"ma_cay:{row.ma_cay}", table="demand_transfer_logs", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    q_ret = _filter_dt(db.query(ReturnEvent), ReturnEvent.created_at, from_day=from_day, to_day=to_day)
    for row in q_ret.all():
        _add_event(events, entity=f"ma_cay:{row.ma_cay}", table="return_events", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    q_issue = _filter_dt(
        db.query(Issue, IssueLine.ma_cay).join(IssueLine, IssueLine.issue_id == Issue.id),
        Issue.created_at,
        from_day=from_day,
        to_day=to_day,
    )
    for issue, ma_cay in q_issue.all():
        _add_event(events, entity=f"ma_cay:{ma_cay}", table="issues", row_id=issue.id, column="created_at", at=issue.created_at, obj=issue)

    q_session = _filter_dt(db.query(PalletStockCheckSession), PalletStockCheckSession.created_at, from_day=from_day, to_day=to_day)
    for row in q_session.all():
        _add_event(events, entity=f"pallet:{row.vi_tri}", table="pallet_stock_check_sessions", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    q_check = _filter_any_dt(
        db.query(PalletStockCheck),
        [PalletStockCheck.created_at, PalletStockCheck.updated_at],
        from_day=from_day,
        to_day=to_day,
    )
    for row in q_check.all():
        entity = f"ma_cay:{row.ma_cay}" if row.ma_cay else f"pallet:{row.vi_tri}"
        _add_event(events, entity=entity, table="pallet_stock_checks", row_id=row.id, column="created_at", at=row.created_at, obj=row)
        _add_event(events, entity=entity, table="pallet_stock_checks", row_id=row.id, column="updated_at", at=row.updated_at, obj=row)

    return events


def _collect_gon_events(db: Session, *, from_day: date | None, to_day: date | None) -> list[EventRef]:
    events: list[EventRef] = []

    q_stock = _filter_any_dt(
        db.query(GonStockEntry),
        [GonStockEntry.created_at, GonStockEntry.updated_at],
        from_day=from_day,
        to_day=to_day,
    )
    for row in q_stock.all():
        entity = f"gon:{row.gon_type}:{row.vi_tri}"
        _add_event(events, entity=entity, table="gon_stock_entries", row_id=row.id, column="created_at", at=row.created_at, obj=row)
        _add_event(events, entity=entity, table="gon_stock_entries", row_id=row.id, column="updated_at", at=row.updated_at, obj=row)

    q_issue = _filter_dt(db.query(GonIssue), GonIssue.created_at, from_day=from_day, to_day=to_day)
    for row in q_issue.all():
        entity = f"gon:{row.gon_type}:{row.from_vi_tri}"
        _add_event(events, entity=entity, table="gon_issues", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    q_transfer = _filter_dt(db.query(GonTransfer), GonTransfer.created_at, from_day=from_day, to_day=to_day)
    for row in q_transfer.all():
        entity = f"gon:{row.gon_type}:{row.from_vi_tri}:{row.to_vi_tri}"
        _add_event(events, entity=entity, table="gon_transfers", row_id=row.id, column="created_at", at=row.created_at, obj=row)

    return events


def _plan_changes(events: list[EventRef]) -> tuple[list[PlannedChange], int]:
    groups: dict[tuple[str, date], list[EventRef]] = defaultdict(list)
    for event in events:
        groups[(event.entity, _to_local(event.at).date())].append(event)

    proposals: dict[tuple[str, int, str], list[PlannedChange]] = defaultdict(list)
    for grouped_events in groups.values():
        for change in _fit_group(grouped_events):
            proposals[change.ref.key].append(change)

    conflicts = 0
    resolved: list[PlannedChange] = []
    for changes in proposals.values():
        if len({c.new_at for c in changes}) > 1:
            conflicts += 1
        # Shared rows, e.g. one issue with many ma_cay, use the latest proposed time
        # so the document never moves before a roll-specific prerequisite event.
        resolved.append(max(changes, key=lambda c: _as_utc(c.new_at)))

    return sorted(resolved, key=lambda item: (item.ref.table, item.ref.row_id, item.ref.column)), conflicts


def _print_plan(changes: list[PlannedChange], *, conflicts: int, limit: int) -> None:
    print(f"Planned timestamp changes: {len(changes)}")
    if conflicts:
        print(f"Shared-row conflicts resolved by latest proposed timestamp: {conflicts}")
    by_table: dict[str, int] = defaultdict(int)
    for change in changes:
        by_table[change.ref.table] += 1
    for table, count in sorted(by_table.items()):
        print(f"- {table}: {count}")

    if not changes:
        return

    print("")
    print("Sample changes:")
    for change in changes[:limit]:
        old_local = _to_local(change.ref.at).strftime("%Y-%m-%d %H:%M:%S")
        new_local = _to_local(change.new_at).strftime("%Y-%m-%d %H:%M:%S")
        print(f"- {change.ref.table}#{change.ref.row_id}.{change.ref.column}: {old_local} -> {new_local} ({change.ref.entity})")


def normalize_event_work_hours(
    db: Session,
    *,
    from_day: date | None,
    to_day: date | None,
    scope: str,
    execute: bool,
    sample_limit: int,
) -> int:
    events: list[EventRef] = []
    if scope in {"fabric", "all"}:
        events.extend(_collect_fabric_events(db, from_day=from_day, to_day=to_day))
    if scope in {"gon", "all"}:
        events.extend(_collect_gon_events(db, from_day=from_day, to_day=to_day))

    changes, conflicts = _plan_changes(events)
    _print_plan(changes, conflicts=conflicts, limit=sample_limit)

    if not execute:
        return len(changes)

    for change in changes:
        setattr(change.ref.obj, change.ref.column, change.new_at)
        db.add(change.ref.obj)
    return len(changes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move operational event timestamps into working hours while preserving per-entity chronology."
    )
    parser.add_argument("--from-date", help="Local date lower bound, YYYY-MM-DD.")
    parser.add_argument("--to-date", help="Local date upper bound, YYYY-MM-DD.")
    parser.add_argument("--scope", choices=("fabric", "gon", "all"), default="fabric")
    parser.add_argument("--execute", action="store_true", help="Write changes. Omit for dry-run.")
    parser.add_argument("--sample-limit", type=int, default=50)
    args = parser.parse_args()

    from_day = _parse_date(args.from_date, field_name="--from-date")
    to_day = _parse_date(args.to_date, field_name="--to-date")
    if from_day and to_day and from_day > to_day:
        raise SystemExit("--from-date must be <= --to-date")

    db = SessionLocal()
    try:
        changed = normalize_event_work_hours(
            db,
            from_day=from_day,
            to_day=to_day,
            scope=args.scope,
            execute=bool(args.execute),
            sample_limit=max(args.sample_limit, 0),
        )
        if args.execute:
            db.commit()
            print(f"Committed {changed} timestamp changes.")
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
