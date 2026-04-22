from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.demand_transfer_log import DemandTransferLog
from fabric_warehouse.db.models.fabric_roll import FabricRoll
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.location_transfer_log import LocationTransferLog
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent
from fabric_warehouse.db.models.stock_check import StockCheck
from fabric_warehouse.db.session import SessionLocal
from fabric_warehouse.wms.location_service import assign_location
from fabric_warehouse.wms.tools_service import transfer_demand, transfer_location


@dataclass(frozen=True)
class SeedOptions:
    nhu_cau: str
    lot: str
    anh_mau: str
    vi_tri_in: str
    vi_tri_move: str
    issue_date: date
    return_date: date


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _norm_ma_cays(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for it in items:
        s = (it or "").strip()
        if not s:
            continue
        out.append(s)
    # preserve order, de-dupe
    return list(dict.fromkeys(out))


def purge_by_ma_cay(db: Session, ma_cays: list[str]) -> dict[str, int]:
    ma_cays = _norm_ma_cays(ma_cays)
    if not ma_cays:
        return {}

    deleted: dict[str, int] = {}

    # Return events first (FK -> issue_lines)
    deleted["return_events"] = int(
        db.query(ReturnEvent).filter(ReturnEvent.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )

    # Issue lines and possibly issues
    issue_ids = [
        r[0]
        for r in db.query(IssueLine.issue_id)
        .filter(IssueLine.ma_cay.in_(ma_cays))
        .distinct()
        .all()
        if r[0] is not None
    ]
    deleted["issue_lines"] = int(
        db.query(IssueLine).filter(IssueLine.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )
    if issue_ids:
        # Delete issues that no longer have lines
        empty_issue_ids = [
            issue_id
            for (issue_id,) in db.query(Issue.id)
            .filter(Issue.id.in_(issue_ids))
            .filter(~Issue.lines.any())
            .all()
        ]
        if empty_issue_ids:
            deleted["issues"] = int(
                db.query(Issue).filter(Issue.id.in_(empty_issue_ids)).delete(synchronize_session=False)
            )

    # Transfer logs / assignments / checks
    deleted["demand_transfer_logs"] = int(
        db.query(DemandTransferLog).filter(DemandTransferLog.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )
    deleted["location_transfer_logs"] = int(
        db.query(LocationTransferLog).filter(LocationTransferLog.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )
    deleted["location_assignments"] = int(
        db.query(LocationAssignment).filter(LocationAssignment.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )
    deleted["stock_checks"] = int(
        db.query(StockCheck).filter(StockCheck.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )

    # Receipts/lines
    receipt_ids = [
        r[0]
        for r in db.query(ReceiptLine.receipt_id)
        .filter(ReceiptLine.ma_cay.in_(ma_cays))
        .distinct()
        .all()
        if r[0] is not None
    ]
    deleted["receipt_lines"] = int(
        db.query(ReceiptLine).filter(ReceiptLine.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )
    if receipt_ids:
        empty_receipt_ids = [
            receipt_id
            for (receipt_id,) in db.query(Receipt.id)
            .filter(Receipt.id.in_(receipt_ids))
            .filter(~Receipt.lines.any())
            .all()
        ]
        if empty_receipt_ids:
            deleted["receipts"] = int(
                db.query(Receipt).filter(Receipt.id.in_(empty_receipt_ids)).delete(synchronize_session=False)
            )

    deleted["fabric_rolls"] = int(
        db.query(FabricRoll).filter(FabricRoll.ma_cay.in_(ma_cays)).delete(synchronize_session=False)
    )

    return {k: v for k, v in deleted.items() if v}


def purge_all_wms(db: Session) -> dict[str, int]:
    deleted: dict[str, int] = {}

    # Order matters due to FK constraints
    deleted["return_events"] = int(db.query(ReturnEvent).delete(synchronize_session=False))
    deleted["issue_lines"] = int(db.query(IssueLine).delete(synchronize_session=False))
    deleted["issues"] = int(db.query(Issue).delete(synchronize_session=False))

    deleted["demand_transfer_logs"] = int(db.query(DemandTransferLog).delete(synchronize_session=False))
    deleted["location_transfer_logs"] = int(db.query(LocationTransferLog).delete(synchronize_session=False))
    deleted["location_assignments"] = int(db.query(LocationAssignment).delete(synchronize_session=False))
    deleted["stock_checks"] = int(db.query(StockCheck).delete(synchronize_session=False))

    deleted["receipt_lines"] = int(db.query(ReceiptLine).delete(synchronize_session=False))
    deleted["receipts"] = int(db.query(Receipt).delete(synchronize_session=False))

    deleted["fabric_rolls"] = int(db.query(FabricRoll).delete(synchronize_session=False))

    return {k: v for k, v in deleted.items() if v}


def seed_scenario(db: Session, *, ma_cays: list[str], opt: SeedOptions) -> dict[str, int]:
    ma_cays = _norm_ma_cays(ma_cays)
    if not ma_cays:
        return {}

    created: dict[str, int] = {}
    now = _now_utc()

    # Fabric rolls (optional but keeps receipt_lines.roll_id semantics available later)
    rolls: list[FabricRoll] = []
    for ma in ma_cays:
        rolls.append(FabricRoll(ma_cay=ma, created_at=now))
    db.add_all(rolls)
    db.flush()
    roll_id_by_ma = {r.ma_cay: r.id for r in rolls}
    created["fabric_rolls"] = len(rolls)

    receipt = Receipt(source_filename="seed_reset_wms_test_data", receipt_date=opt.issue_date, note="seed data")
    db.add(receipt)
    db.flush()
    created["receipts"] = 1

    lines: list[ReceiptLine] = []
    checks: list[StockCheck] = []
    for idx, ma in enumerate(ma_cays):
        yards = float(50 + idx * 10)
        lines.append(
            ReceiptLine(
                receipt_id=receipt.id,
                roll_id=roll_id_by_ma.get(ma),
                ma_cay=ma,
                nhu_cau=opt.nhu_cau,
                lot=opt.lot,
                anh_mau=opt.anh_mau,
                yards=yards,
                raw_data={},
                created_at=now,
            )
        )
        checks.append(
            StockCheck(
                nhu_cau=opt.nhu_cau,
                lot=opt.lot,
                ma_cay=ma,
                expected_yards=yards,
                actual_yards=yards,
                note="seed stock_check",
                updated_at=now,
            )
        )
    db.add_all(lines)
    db.add_all(checks)
    created["receipt_lines"] = len(lines)
    created["stock_checks"] = len(checks)

    # "Nhập kho" by assigning to location (also writes first LocationTransferLog with from_vi_tri NULL)
    assign_location(
        db,
        nhu_cau=opt.nhu_cau,
        lot=opt.lot,
        anh_mau=opt.anh_mau,
        ma_cays=ma_cays,
        vi_tri=opt.vi_tri_in,
    )
    created["location_assignments"] = len(ma_cays)

    # Move location (creates LocationTransferLog)
    transfer_location(db, ma_cays=ma_cays, to_vi_tri=opt.vi_tri_move, note="seed move")

    # Transfer demand (creates DemandTransferLog)
    transfer_demand(db, ma_cays=ma_cays, to_nhu_cau=f"{opt.nhu_cau}-MOVE", to_lot=opt.lot, note="seed transfer")

    # Issue (export)
    issue = Issue(nhu_cau=opt.nhu_cau, lot=opt.lot, ngay_xuat=opt.issue_date, note="seed issue")
    db.add(issue)
    db.flush()
    ilines: list[IssueLine] = []
    for ma in ma_cays:
        ilines.append(
            IssueLine(
                issue_id=issue.id,
                ma_cay=ma,
                so_luong_xuat=10.0,
                vi_tri=opt.vi_tri_move,
            )
        )
    db.add_all(ilines)
    created["issues"] = 1
    created["issue_lines"] = len(ilines)

    # Return event for first roll
    db.flush()
    first_line_id = ilines[0].id if ilines else None
    if first_line_id:
        re = ReturnEvent(
            issue_line_id=first_line_id,
            ma_cay=ma_cays[0],
            ngay_tai_nhap=opt.return_date,
            yds_du=5.0,
            status="Tái nhập kho",
            nhu_cau_moi=f"{opt.nhu_cau}-RTN",
            lot_moi=f"{opt.lot}-R",
            vi_tri_moi=opt.vi_tri_in,
            note="seed return",
            created_at=now,
        )
        db.add(re)
        created["return_events"] = 1

    # Count logs created by triggers/services
    created["location_transfer_logs"] = int(
        db.execute(
            select(func.count(LocationTransferLog.id)).where(LocationTransferLog.ma_cay.in_(ma_cays))
        ).scalar_one()
    )
    created["demand_transfer_logs"] = int(
        db.execute(
            select(func.count(DemandTransferLog.id)).where(DemandTransferLog.ma_cay.in_(ma_cays))
        ).scalar_one()
    )

    return {k: v for k, v in created.items() if v}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="reset_wms_test_data",
        description="Purge/seed WMS data for testing endpoints (/trace, layout, ...).",
    )
    p.add_argument("--yes", action="store_true", help="Required for destructive operations.")
    p.add_argument("--all", action="store_true", help="Purge ALL WMS transactional data (danger).")
    p.add_argument("--ma-cay", nargs="*", default=[], help="Roll ids (ma_cay) to purge/seed.")
    p.add_argument("--recreate", action="store_true", help="Purge then seed the same ma_cay list.")

    p.add_argument("--seed", action="store_true", help="Seed a test scenario for the given ma_cay list.")
    p.add_argument("--nhu-cau", default="NC-TEST", help="Seed nhu_cau.")
    p.add_argument("--lot", default="LOT-TEST", help="Seed lot.")
    p.add_argument("--anh-mau", default="CHUNG", help="Seed anh_mau.")
    p.add_argument("--vi-tri-in", default="A.01.01", help="Initial storage location.")
    p.add_argument("--vi-tri-move", default="A.01.02", help="Move-to location for transfer event.")
    p.add_argument("--issue-date", default="", help="Issue date YYYY-MM-DD (default: today).")
    p.add_argument("--return-date", default="", help="Return date YYYY-MM-DD (default: today+1).")

    args = p.parse_args(argv)

    if (args.all or args.ma_cay or args.recreate) and not args.yes:
        print("Refusing to run: add --yes to confirm destructive changes.", file=sys.stderr)
        return 2

    ma_cays = _norm_ma_cays(args.ma_cay)
    if not args.all and not ma_cays:
        print("Nothing to do: provide --all or --ma-cay ...", file=sys.stderr)
        return 2

    issue_day = date.today()
    if args.issue_date:
        issue_day = date.fromisoformat(args.issue_date)
    return_day = issue_day + timedelta(days=1)
    if args.return_date:
        return_day = date.fromisoformat(args.return_date)

    seed_opt = SeedOptions(
        nhu_cau=(args.nhu_cau or "NC-TEST").strip(),
        lot=(args.lot or "LOT-TEST").strip(),
        anh_mau=(args.anh_mau or "CHUNG").strip() or "CHUNG",
        vi_tri_in=(args.vi_tri_in or "A.01.01").strip(),
        vi_tri_move=(args.vi_tri_move or "A.01.02").strip(),
        issue_date=issue_day,
        return_date=return_day,
    )

    db = SessionLocal()
    try:
        deleted: dict[str, int] = {}
        created: dict[str, int] = {}

        if args.all:
            deleted = purge_all_wms(db)
        else:
            deleted = purge_by_ma_cay(db, ma_cays)

        if args.recreate or args.seed:
            created = seed_scenario(db, ma_cays=ma_cays, opt=seed_opt)

        db.commit()
        if deleted:
            print("Deleted:")
            for k, v in deleted.items():
                print(f"  - {k}: {v}")
        if created:
            print("Seeded:")
            for k, v in created.items():
                print(f"  - {k}: {v}")
        if not deleted and not created:
            print("No changes.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

