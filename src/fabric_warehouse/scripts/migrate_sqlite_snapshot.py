from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.models.fabric_roll import FabricRoll
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.stock_check import StockCheck
from fabric_warehouse.db.session import SessionLocal


@dataclass(frozen=True)
class StoredRollRow:
    nhu_cau: str
    lot: str
    ma_cay: str
    vi_tri: str
    anh_mau: str | None
    assigned_at: datetime | None
    updated_at: datetime | None
    actual_yards: float | None
    expected_yards: float | None


def _dt_from_iso(s: str | None) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        # Old SQLite timestamps were saved as local naive; treat as UTC for storage.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _open_sqlite(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def load_stored_rolls_from_wms_sqlite(*, wms_db_path: str) -> list[StoredRollRow]:
    con = _open_sqlite(wms_db_path)
    try:
        cur = con.cursor()
        stored = cur.execute(
            """
            SELECT
              nhu_cau,
              lot,
              ma_cay,
              vi_tri,
              ngay_cap_nhat,
              trang_thai,
              "Ành màu" AS anh_mau
            FROM vi_tri_data
            WHERE trang_thai = 'Đang lưu'
              AND ma_cay IS NOT NULL AND ma_cay <> ''
              AND lot IS NOT NULL AND lot <> ''
              AND nhu_cau IS NOT NULL AND nhu_cau <> ''
              AND vi_tri IS NOT NULL AND vi_tri <> ''
            """
        ).fetchall()

        keys = {(r["nhu_cau"], r["lot"], r["ma_cay"]) for r in stored}
        checks: dict[tuple[str, str, str], sqlite3.Row] = {}
        if keys:
            # kiemkho_data has the qty we want (thuc_te), fallback to so_luong
            rows = cur.execute(
                """
                SELECT
                  nhu_cau,
                  lot,
                  ma_cay,
                  so_luong,
                  thuc_te,
                  ngay_cap_nhat
                FROM kiemkho_data
                WHERE ma_cay IS NOT NULL AND ma_cay <> ''
                """
            ).fetchall()
            for r in rows:
                k = (r["nhu_cau"], r["lot"], r["ma_cay"])
                if k in keys and k not in checks:
                    checks[k] = r

        out: list[StoredRollRow] = []
        for r in stored:
            nhu_cau = str(r["nhu_cau"]).strip()
            lot = str(r["lot"]).strip()
            ma_cay = str(r["ma_cay"]).strip()
            vi_tri = str(r["vi_tri"]).strip()
            anh_mau = str(r["anh_mau"]).strip() if r["anh_mau"] is not None else None
            updated_at = _dt_from_iso(r["ngay_cap_nhat"])

            ck = checks.get((nhu_cau, lot, ma_cay))
            expected = _as_float(ck["so_luong"]) if ck is not None else None
            actual = _as_float(ck["thuc_te"]) if ck is not None else None
            if actual is None:
                actual = expected

            assigned_at = updated_at
            check_updated = _dt_from_iso(ck["ngay_cap_nhat"]) if ck is not None else None
            if check_updated and (updated_at is None or check_updated > updated_at):
                updated_at = check_updated
            if check_updated and (assigned_at is None or check_updated < assigned_at):
                assigned_at = check_updated

            out.append(
                StoredRollRow(
                    nhu_cau=nhu_cau,
                    lot=lot,
                    ma_cay=ma_cay,
                    vi_tri=vi_tri,
                    anh_mau=anh_mau,
                    assigned_at=assigned_at,
                    updated_at=updated_at,
                    actual_yards=actual,
                    expected_yards=expected,
                )
            )
        return out
    finally:
        con.close()


def load_fabric_norms_from_sqlite(*, fabric_db_path: str) -> list[dict[str, object]]:
    con = _open_sqlite(fabric_db_path)
    try:
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT
              "Mã Model" AS ma_model,
              "Tên Model" AS ten_model,
              "Ghi chú" AS ghi_chu,
              "YRD/Pallet" AS yrd_per_pallet,
              "USD/YRD" AS usd_per_yrd,
              *
            FROM fabric_table
            """
        ).fetchall()
        out: list[dict[str, object]] = []
        for r in rows:
            ma_model = str(r["ma_model"] or "").strip()
            if not ma_model:
                continue
            out.append(
                {
                    "ma_model": ma_model,
                    "ten_model": str(r["ten_model"] or "").strip() or None,
                    "ghi_chu": str(r["ghi_chu"] or "").strip() or None,
                    "yrd_per_pallet": _as_float(r["yrd_per_pallet"]),
                    "usd_per_yrd": _as_float(r["usd_per_yrd"]),
                    "raw_data": dict(r),
                }
            )
        return out
    finally:
        con.close()


def upsert_stored_rolls(db: Session, rows: list[StoredRollRow]) -> dict[str, int]:
    created_rolls = 0
    upsert_assign = 0
    upsert_checks = 0

    now = datetime.now(timezone.utc)

    for r in rows:
        ma = r.ma_cay
        existing_roll = db.query(FabricRoll).filter(FabricRoll.ma_cay == ma).first()
        if not existing_roll:
            db.add(FabricRoll(ma_cay=ma, created_at=(r.assigned_at or now)))
            created_rolls += 1

        sc = (
            db.query(StockCheck)
            .filter(StockCheck.nhu_cau == r.nhu_cau)
            .filter(StockCheck.lot == r.lot)
            .filter(StockCheck.ma_cay == r.ma_cay)
            .first()
        )
        if not sc:
            sc = StockCheck(
                nhu_cau=r.nhu_cau,
                lot=r.lot,
                ma_cay=r.ma_cay,
                expected_yards=r.expected_yards,
                actual_yards=r.actual_yards,
                updated_at=(r.updated_at or now),
            )
            db.add(sc)
            upsert_checks += 1
        else:
            sc.expected_yards = r.expected_yards
            sc.actual_yards = r.actual_yards
            if r.updated_at:
                sc.updated_at = r.updated_at
            db.add(sc)

        la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == r.ma_cay).first()
        if not la:
            la = LocationAssignment(
                ma_cay=r.ma_cay,
                nhu_cau=r.nhu_cau,
                lot=r.lot,
                anh_mau=r.anh_mau,
                vi_tri=r.vi_tri,
                trang_thai="Đang lưu",
                assigned_at=(r.assigned_at or now),
                updated_at=(r.updated_at or now),
            )
            db.add(la)
            upsert_assign += 1
        else:
            la.nhu_cau = r.nhu_cau
            la.lot = r.lot
            la.anh_mau = r.anh_mau
            la.vi_tri = r.vi_tri
            la.trang_thai = "Đang lưu"
            if getattr(la, "assigned_at", None) is None:
                la.assigned_at = r.assigned_at or now
            if r.updated_at:
                la.updated_at = r.updated_at
            db.add(la)

    return {
        "fabric_rolls_created": created_rolls,
        "location_assignments_upserted": upsert_assign,
        "stock_checks_upserted": upsert_checks,
    }


def upsert_fabric_norms(db: Session, norms: list[dict[str, object]]) -> dict[str, int]:
    upserted = 0
    for it in norms:
        ma_model = str(it.get("ma_model") or "").strip()
        if not ma_model:
            continue
        row = db.query(FabricData).filter(FabricData.ma_model == ma_model).first()
        if not row:
            row = FabricData(ma_model=ma_model)
        row.ten_model = it.get("ten_model")  # type: ignore[assignment]
        row.ghi_chu = it.get("ghi_chu")  # type: ignore[assignment]
        row.yrd_per_pallet = it.get("yrd_per_pallet")  # type: ignore[assignment]
        row.usd_per_yrd = it.get("usd_per_yrd")  # type: ignore[assignment]
        row.raw_data = it.get("raw_data") or {}  # type: ignore[assignment]
        db.add(row)
        upserted += 1
    return {"fabric_data_upserted": upserted}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="migrate_sqlite_snapshot",
        description="Migrate a snapshot of legacy SQLite (wms.db / fabric.db) into the new Postgres schema.",
    )
    p.add_argument("--yes", action="store_true", help="Confirm write to Postgres.")
    p.add_argument("--dry-run", action="store_true", help="Load and print stats without writing.")
    p.add_argument("--wms-db", required=True, help="Path to legacy wms.db (SQLite).")
    p.add_argument("--fabric-db", default="", help="Optional path to legacy fabric.db (SQLite).")
    p.add_argument("--import-norms", action="store_true", help="Also import fabric norms into fabric_data.")
    args = p.parse_args(argv)

    rows = load_stored_rolls_from_wms_sqlite(wms_db_path=args.wms_db)
    print(f"Found stored rolls: {len(rows)}")
    if rows:
        print("Sample:")
        for r in rows[:5]:
            print(f"  - {r.ma_cay} | {r.nhu_cau}/{r.lot} | {r.vi_tri} | yds={r.actual_yards}")

    norms: list[dict[str, object]] = []
    if args.import_norms:
        if not args.fabric_db:
            print("Missing --fabric-db for --import-norms", file=sys.stderr)
            return 2
        norms = load_fabric_norms_from_sqlite(fabric_db_path=args.fabric_db)
        print(f"Found fabric norms: {len(norms)}")

    if args.dry_run:
        print("Dry-run: no writes.")
        return 0

    if not args.yes:
        print("Refusing to write: add --yes (or use --dry-run).", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        stats: dict[str, int] = {}
        stats.update(upsert_stored_rolls(db, rows))
        if norms:
            stats.update(upsert_fabric_norms(db, norms))
        db.commit()
        print("Done. Stats:")
        for k, v in stats.items():
            print(f"  - {k}: {v}")
        return 0
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
