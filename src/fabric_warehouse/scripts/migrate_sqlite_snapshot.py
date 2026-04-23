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
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.stock_check import StockCheck
from fabric_warehouse.db.session import SessionLocal
from fabric_warehouse.wms.receipts_service import _extract_ma_hang, _format_code


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


def _date_from_any(s: str | None) -> datetime | None:
    """
    Parse legacy date strings found in SQLite (excel_data).

    Common formats:
    - yyyy-mm-dd
    - dd/mm/yyyy
    - hh:mm dd/mm/yyyy
    """
    s = (s or "").strip()
    if not s:
        return None
    try:
        # ISO-like or full datetime
        return _dt_from_iso(s)
    except Exception:
        pass

    import re

    m = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", s)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(yy, mm, dd, tzinfo=timezone.utc)
        except Exception:
            return None
    return None


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


def load_excel_rows_from_wms_sqlite(*, wms_db_path: str) -> list[dict[str, object]]:
    """
    Load raw rows from legacy excel_data table.

    These rows contain the fields needed for reports (loai_vai/mau_vai) and for
    building HangingTag metadata.
    """
    con = _open_sqlite(wms_db_path)
    try:
        cur = con.cursor()
        rows = cur.execute('SELECT * FROM excel_data').fetchall()
        return [dict(r) for r in rows]
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


def _parse_ngay_xuat(s: str | None) -> object | None:
    """
    Legacy "Ngày xuất" often looks like '10:07 12/12/2025'.
    Store only the date part.
    """
    dt = _date_from_any(s)
    return dt.date() if isinstance(dt, datetime) else None


def upsert_excel_metadata(
    db: Session,
    *,
    wms_db_path: str,
    only_ma_cays: set[str] | None = None,
) -> dict[str, int]:
    """
    Import excel_data into Postgres so reports by loai_vai/mau_vai work.

    Creates synthetic Receipts + ReceiptLines and HangingTags.
    """
    excel_rows = load_excel_rows_from_wms_sqlite(wms_db_path=wms_db_path)
    if not excel_rows:
        return {"receipts_created": 0, "receipt_lines_upserted": 0, "hanging_tags_upserted": 0}

    # Filter to only rolls we actually have stored (optional, speeds up big DBs).
    if only_ma_cays is not None:
        filtered: list[dict[str, object]] = []
        for r in excel_rows:
            ma = str(r.get("Mã cây") or "").strip()
            if ma and ma in only_ma_cays:
                filtered.append(r)
        excel_rows = filtered

    # Group rows by "Ngày nhập hàng" (fallback "Ngày nhập"). Each group becomes 1 synthetic receipt.
    groups: dict[str, list[dict[str, object]]] = {}
    for r in excel_rows:
        ma_cay = str(r.get("Mã cây") or "").strip()
        if not ma_cay:
            continue
        d0 = _date_from_any(str(r.get("Ngày nhập hàng") or "")) or _date_from_any(str(r.get("Ngày nhập") or ""))
        day_key = d0.date().isoformat() if isinstance(d0, datetime) else "unknown"
        groups.setdefault(day_key, []).append(r)

    now = datetime.now(timezone.utc)
    receipts_created = 0
    lines_upserted = 0
    tags_upserted = 0

    for day_key, rows in groups.items():
        receipt_date = None
        if day_key != "unknown":
            try:
                receipt_date = datetime.fromisoformat(day_key).date()
            except Exception:
                receipt_date = None

        source_filename = f"sqlite_excel_data::{day_key}"
        receipt = (
            db.query(Receipt)
            .filter(Receipt.source_filename == source_filename)
            .first()
        )
        if not receipt:
            receipt = Receipt(source_filename=source_filename, receipt_date=receipt_date)
            db.add(receipt)
            db.flush()
            receipts_created += 1

        # Ensure FabricRoll exists for roll_id FK.
        ma_cays = []
        for r in rows:
            ma = str(r.get("Mã cây") or "").strip()
            if ma:
                ma_cays.append(ma)
        ma_cays = list(dict.fromkeys(ma_cays))

        existing_rolls = db.query(FabricRoll).filter(FabricRoll.ma_cay.in_(ma_cays)).all() if ma_cays else []
        roll_id_by_ma = {x.ma_cay: x.id for x in existing_rolls}
        for ma in ma_cays:
            if ma in roll_id_by_ma:
                continue
            fr = FabricRoll(ma_cay=ma, created_at=now)
            db.add(fr)
            db.flush()
            roll_id_by_ma[ma] = fr.id

        # Upsert receipt_lines by unique (receipt_id, ma_cay).
        existing_lines = (
            db.query(ReceiptLine.ma_cay)
            .filter(ReceiptLine.receipt_id == receipt.id)
            .filter(ReceiptLine.ma_cay.in_(ma_cays))
            .all()
        )
        existing_ma = {str(x[0]) for x in existing_lines if x and x[0]}

        for r in rows:
            ma_cay = str(r.get("Mã cây") or "").strip()
            if not ma_cay or ma_cay in existing_ma:
                continue

            nhu_cau = str(r.get("Nhu cầu") or "").strip() or None
            lot = str(r.get("Lot") or "").strip() or None
            anh_mau = str(r.get("Ành màu") or "").strip() or None
            if anh_mau:
                anh_mau = _format_code(anh_mau) or anh_mau

            yards = _as_float(r.get("Số lượng"))
            art = _format_code(r.get("Mã Art"))

            line = ReceiptLine(
                receipt_id=receipt.id,
                roll_id=roll_id_by_ma.get(ma_cay),
                ma_cay=ma_cay,
                nhu_cau=nhu_cau,
                lot=lot,
                anh_mau=anh_mau or "CHUNG",
                model=None,
                art=art,
                yards=yards,
                raw_data=dict(r),
            )
            db.add(line)
            lines_upserted += 1
            existing_ma.add(ma_cay)

        # Upsert hanging_tag per (nhu_cau, lot) for this receipt.
        # Pick the first row encountered for each (nhu_cau, lot).
        by_key: dict[tuple[str | None, str | None], dict[str, object]] = {}
        for r in rows:
            nhu_cau = str(r.get("Nhu cầu") or "").strip() or None
            lot = str(r.get("Lot") or "").strip() or None
            if not lot:
                continue
            key = (nhu_cau, lot)
            if key in by_key:
                continue
            by_key[key] = r

        for (nhu_cau, lot), r in by_key.items():
            id_bang_treo = f"{(nhu_cau or '')}-{(lot or '')}-{receipt_date.isoformat() if receipt_date else ''}"
            tag = db.query(HangingTag).filter(HangingTag.id_bang_treo == id_bang_treo).first()
            if not tag:
                tag = HangingTag(receipt_id=receipt.id, id_bang_treo=id_bang_treo)

            customer = _format_code(r.get("Customer"))
            tag.ngay_nhap_hang = receipt_date  # type: ignore[assignment]
            tag.nhu_cau = nhu_cau  # type: ignore[assignment]
            tag.lot = lot  # type: ignore[assignment]
            tag.ma_hang = _extract_ma_hang(nhu_cau)  # type: ignore[assignment]
            tag.customer = customer  # type: ignore[assignment]
            tag.nha_cung_cap = customer  # type: ignore[assignment]
            tag.khach_hang = "DECATHLON"  # type: ignore[assignment]
            tag.ngay_xuat = _parse_ngay_xuat(str(r.get("Ngày xuất") or ""))  # type: ignore[assignment]

            tag.loai_vai = _format_code(r.get("Tên Art"))  # type: ignore[assignment]
            tag.ma_art = _format_code(r.get("Mã Art"))  # type: ignore[assignment]
            tag.mau_vai = _format_code(r.get("Tên Màu"))  # type: ignore[assignment]
            tag.ma_mau = _format_code(r.get("Mã Màu"))  # type: ignore[assignment]
            tag.ket_qua_kiem_tra = "OK"  # type: ignore[assignment]

            db.add(tag)
            tags_upserted += 1

    return {
        "receipts_created": receipts_created,
        "receipt_lines_upserted": lines_upserted,
        "hanging_tags_upserted": tags_upserted,
    }


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

        # Import excel_data metadata so reports by loai_vai/mau_vai work for migrated rolls.
        try:
            only_ma = {r.ma_cay for r in rows if r.ma_cay}
        except Exception:
            only_ma = None
        stats.update(upsert_excel_metadata(db, wms_db_path=args.wms_db, only_ma_cays=only_ma))
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
