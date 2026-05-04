from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.models.fabric_roll import FabricRoll
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.issue import Issue, IssueLine
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.db.models.return_event import ReturnEvent
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
    # ISO-like or full datetime
    dt = _dt_from_iso(s)
    if dt is not None:
        return dt

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


def _limit_text(v: object, max_len: int) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:max_len]


def _format_limited(v: object, max_len: int, *, default: str | None = None) -> str | None:
    formatted = _format_code(v)
    return _limit_text(formatted or v or default, max_len)


def _open_sqlite(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def _ascii_fold(value: object | None) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _is_valid_legacy_ma_cay(value: object | None) -> bool:
    ma_cay = str(value or "").strip()
    if not ma_cay:
        return False
    folded = _ascii_fold(ma_cay)
    if re.fullmatch(r"\d+\s*cay", folded):
        return False
    return True


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
        return [dict(r) for r in rows if _is_valid_legacy_ma_cay(_row_value(r, "ma cay"))]
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
                nhu_cau=_limit_text(r.nhu_cau, 64) or "UNKNOWN",
                lot=_limit_text(r.lot, 64) or "UNKNOWN",
                ma_cay=r.ma_cay,
                expected_yards=r.expected_yards,
                actual_yards=r.actual_yards,
                updated_at=(r.updated_at or now),
            )
            db.add(sc)
            upsert_checks += 1
        else:
            sc.nhu_cau = _limit_text(r.nhu_cau, 64) or sc.nhu_cau
            sc.lot = _limit_text(r.lot, 64) or sc.lot
            sc.expected_yards = r.expected_yards
            sc.actual_yards = r.actual_yards
            if r.updated_at:
                sc.updated_at = r.updated_at
            db.add(sc)

        la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == r.ma_cay).first()
        if not la:
            la = LocationAssignment(
                ma_cay=r.ma_cay,
                nhu_cau=_limit_text(r.nhu_cau, 64) or "UNKNOWN",
                lot=_limit_text(r.lot, 64) or "UNKNOWN",
                anh_mau=_limit_text(r.anh_mau, 64),
                vi_tri=r.vi_tri,
                trang_thai="Đang lưu",
                assigned_at=(r.assigned_at or now),
                updated_at=(r.updated_at or now),
            )
            db.add(la)
            upsert_assign += 1
        else:
            la.nhu_cau = _limit_text(r.nhu_cau, 64) or la.nhu_cau
            la.lot = _limit_text(r.lot, 64) or la.lot
            la.anh_mau = _limit_text(r.anh_mau, 64)
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


def _legacy_rows_by_ma(
    con: sqlite3.Connection,
    *,
    table: str,
    ma_col: str,
) -> dict[str, sqlite3.Row]:
    cur = con.cursor()
    resolved_ma_col = _resolve_sqlite_column_name(con, table=table, wanted=ma_col)
    if resolved_ma_col is None:
        return {}
    try:
        rows = cur.execute(
            f'SELECT * FROM "{table}" WHERE "{resolved_ma_col}" IS NOT NULL AND "{resolved_ma_col}" <> ""'
        ).fetchall()
    except sqlite3.Error:
        return {}
    out: dict[str, sqlite3.Row] = {}
    for r in rows:
        ma = str(_row_value(r, ma_col) or "").strip()
        if _is_valid_legacy_ma_cay(ma) and ma not in out:
            out[ma] = r
    return out


def _resolve_sqlite_column_name(con: sqlite3.Connection, *, table: str, wanted: str) -> str | None:
    cur = con.cursor()
    try:
        rows = cur.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error:
        return None
    wanted_folded = _ascii_fold(wanted)
    for row in rows:
        name = row[1] if isinstance(row, tuple) else row["name"]
        if _ascii_fold(name) == wanted_folded:
            return str(name)
    return None


def _existing_postgres_ma_cays(db: Session) -> set[str]:
    out: set[str] = set()
    for model in (FabricRoll, ReceiptLine, StockCheck, LocationAssignment, IssueLine, ReturnEvent):
        try:
            for (ma,) in db.query(model.ma_cay).filter(model.ma_cay.isnot(None)).all():
                ma_s = str(ma or "").strip()
                if ma_s:
                    out.add(ma_s)
        except Exception:
            continue
    return out


def _row_value(row: sqlite3.Row | None, *keys: str) -> object | None:
    if row is None:
        return None
    available = {_ascii_fold(key): key for key in row.keys()}
    for key in keys:
        resolved = available.get(_ascii_fold(key))
        if resolved is not None:
            return row[resolved]
    return None


def _row_text(row: sqlite3.Row | None, *keys: str) -> str | None:
    value = _row_value(row, *keys)
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _mapping_value(row: dict[str, object] | None, *keys: str) -> object | None:
    if row is None:
        return None
    available = {_ascii_fold(key): key for key in row.keys()}
    for key in keys:
        resolved = available.get(_ascii_fold(key))
        if resolved is not None:
            return row.get(resolved)
    return None


def _mapping_text(row: dict[str, object] | None, *keys: str) -> str | None:
    value = _mapping_value(row, *keys)
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _issue_status(raw: str | None) -> str:
    s = (raw or "").strip()
    if "Trả Mẹ Nhu" in s or "Tra Me Nhu" in s:
        return "Trả Mẹ Nhu"
    return s or "Cấp phát sản xuất"


def _ensure_fabric_roll(db: Session, *, ma_cay: str, created_at: datetime) -> int:
    roll = db.query(FabricRoll).filter(FabricRoll.ma_cay == ma_cay).first()
    if not roll:
        roll = FabricRoll(ma_cay=ma_cay, created_at=created_at)
        db.add(roll)
        db.flush()
    return roll.id


def _receipt_for_legacy_day(db: Session, *, day_key: str, receipt_dt: datetime | None) -> tuple[Receipt, bool]:
    receipt_date = receipt_dt.date() if isinstance(receipt_dt, datetime) else None
    source_filename = f"sqlite_full_history::{day_key}"
    receipt = db.query(Receipt).filter(Receipt.source_filename == source_filename).first()
    if receipt:
        return receipt, False
    receipt = Receipt(
        source_filename=source_filename,
        receipt_date=receipt_date,
        created_at=(receipt_dt if isinstance(receipt_dt, datetime) else datetime.now(timezone.utc)),
    )
    db.add(receipt)
    db.flush()
    return receipt, True


def _issue_for_legacy_day(
    db: Session,
    *,
    nhu_cau: str,
    lot: str,
    ngay_xuat,
    status: str,
) -> tuple[Issue, bool]:
    nhu_cau = _limit_text(nhu_cau, 64) or "UNKNOWN"
    lot = _limit_text(lot, 64) or "UNKNOWN"
    status = _limit_text(status, 64) or "Cấp phát sản xuất"
    issue = (
        db.query(Issue)
        .filter(Issue.nhu_cau == nhu_cau)
        .filter(Issue.lot == lot)
        .filter(Issue.ngay_xuat == ngay_xuat)
        .filter(Issue.status == status)
        .filter(Issue.note.is_(None))
        .first()
    )
    if issue:
        return issue, False
    issue_created_at = datetime.combine(ngay_xuat, datetime.min.time(), tzinfo=timezone.utc)
    issue = Issue(
        nhu_cau=nhu_cau,
        lot=lot,
        ngay_xuat=ngay_xuat,
        status=status,
        created_at=issue_created_at,
    )
    db.add(issue)
    db.flush()
    return issue, True


def import_missing_legacy_history(
    db: Session,
    *,
    wms_db_path: str,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Import legacy rolls not present in the new app, keyed by unique ma_cay.

    This is intended for historical/trace data: missing legacy rolls are treated
    as exported unless legacy state explicitly says otherwise.
    """
    existing_ma = _existing_postgres_ma_cays(db)

    con = _open_sqlite(wms_db_path)
    try:
        excel_by_ma = _legacy_rows_by_ma(con, table="excel_data", ma_col="ma cay")
        check_by_ma = _legacy_rows_by_ma(con, table="kiemkho_data", ma_col="ma_cay")
        loc_by_ma = _legacy_rows_by_ma(con, table="vi_tri_data", ma_col="ma_cay")
        issue_by_ma = _legacy_rows_by_ma(con, table="xuatkho_data", ma_col="ma_cay")
        return_by_ma = _legacy_rows_by_ma(con, table="tai_nhap_kho_data", ma_col="ma_cay")
    finally:
        con.close()

    legacy_ma = set().union(excel_by_ma, check_by_ma, loc_by_ma, issue_by_ma, return_by_ma)
    missing_ma = sorted(ma for ma in legacy_ma if ma and ma not in existing_ma)
    if limit is not None:
        missing_ma = missing_ma[: max(int(limit), 0)]

    now = datetime.now(timezone.utc)
    stats = {
        "legacy_ma_cays_seen": len(legacy_ma),
        "postgres_ma_cays_seen": len(existing_ma),
        "missing_ma_cays_found": len(missing_ma),
        "fabric_rolls_created": 0,
        "receipts_created": 0,
        "receipt_lines_created": 0,
        "stock_checks_created": 0,
        "location_assignments_created": 0,
        "issues_created": 0,
        "issue_lines_created": 0,
        "return_events_created": 0,
    }

    for ma_cay in missing_ma:
        ex = excel_by_ma.get(ma_cay)
        ck = check_by_ma.get(ma_cay)
        loc = loc_by_ma.get(ma_cay)
        iss = issue_by_ma.get(ma_cay)
        ret = return_by_ma.get(ma_cay)

        nhu_cau = (
            _row_text(ex, "nhu cau")
            or _row_text(iss, "nhu_cau")
            or _row_text(ck, "nhu_cau")
            or _row_text(loc, "nhu_cau")
            or _row_text(ret, "nhu_cau_cu")
            or "UNKNOWN"
        )
        lot = (
            _row_text(ex, "lot")
            or _row_text(iss, "lot")
            or _row_text(ck, "lot")
            or _row_text(loc, "lot")
            or _row_text(ret, "lot")
            or "UNKNOWN"
        )

        receipt_dt = (
            _date_from_any(_row_text(ex, "ngay nhap hang"))
            or _date_from_any(_row_text(ex, "ngay nhap"))
            or _dt_from_iso(_row_text(ck, "ngay_cap_nhat"))
            or _dt_from_iso(_row_text(loc, "ngay_cap_nhat"))
            or now
        )
        day_key = receipt_dt.date().isoformat() if isinstance(receipt_dt, datetime) else "unknown"
        roll_id = _ensure_fabric_roll(db, ma_cay=ma_cay, created_at=receipt_dt if isinstance(receipt_dt, datetime) else now)
        if ma_cay not in existing_ma:
            stats["fabric_rolls_created"] += 1
            existing_ma.add(ma_cay)

        receipt, created_receipt = _receipt_for_legacy_day(db, day_key=day_key, receipt_dt=receipt_dt)
        if created_receipt:
            stats["receipts_created"] += 1

        existing_line = db.query(ReceiptLine).filter(ReceiptLine.ma_cay == ma_cay).first()
        expected_yards = _as_float(_row_value(ck, "so_luong")) or _as_float(_row_value(ex, "so luong"))
        actual_yards = _as_float(_row_value(ck, "thuc_te")) or _as_float(_row_value(ex, "thuc_te")) or expected_yards
        anh_mau = _row_text(ex, "anh mau") or _row_text(ck, "anh mau") or _row_text(loc, "anh mau") or "CHUNG"
        if not existing_line:
            db.add(
                ReceiptLine(
                    receipt_id=receipt.id,
                    roll_id=roll_id,
                    ma_cay=ma_cay,
                    nhu_cau=_limit_text(nhu_cau, 64),
                    lot=_limit_text(lot, 64),
                    anh_mau=_format_limited(anh_mau, 64, default="CHUNG") or "CHUNG",
                    model=None,
                    art=_format_limited(_row_value(ex, "ma art"), 64),
                    yards=expected_yards,
                    raw_data=dict(ex) if ex is not None else {},
                )
            )
            stats["receipt_lines_created"] += 1

        existing_sc = (
            db.query(StockCheck)
            .filter(StockCheck.nhu_cau == nhu_cau)
            .filter(StockCheck.lot == lot)
            .filter(StockCheck.ma_cay == ma_cay)
            .first()
        )
        if not existing_sc:
            db.add(
                StockCheck(
                    nhu_cau=_limit_text(nhu_cau, 64) or "UNKNOWN",
                    lot=_limit_text(lot, 64) or "UNKNOWN",
                    ma_cay=ma_cay,
                    expected_yards=expected_yards,
                    actual_yards=actual_yards,
                    note=_limit_text(_row_text(ck, "ghi_chu"), 500),
                    updated_at=(
                        _dt_from_iso(_row_text(ck, "ngay_cap_nhat"))
                        or _dt_from_iso(_row_text(loc, "ngay_cap_nhat"))
                        or receipt_dt
                        or now
                    ),
                )
            )
            stats["stock_checks_created"] += 1

        loc_status = _row_text(loc, "trang_thai")
        issue_date = _parse_ngay_xuat(_row_text(iss, "ngay_xuat")) or _parse_ngay_xuat(_row_text(ex, "ngay xuat"))
        final_status = loc_status or ("Đã xuất" if issue_date or iss is not None else "Đã xuất")
        vi_tri = _row_text(loc, "vi_tri") or _row_text(ck, "vi_tri_pallet") or "N/A"
        existing_la = db.query(LocationAssignment).filter(LocationAssignment.ma_cay == ma_cay).first()
        if not existing_la:
            db.add(
                LocationAssignment(
                    ma_cay=ma_cay,
                    nhu_cau=_limit_text(nhu_cau, 64) or "UNKNOWN",
                    lot=_limit_text(lot, 64) or "UNKNOWN",
                    anh_mau=_format_limited(anh_mau, 64, default="CHUNG") or "CHUNG",
                    vi_tri=vi_tri[:16],
                    trang_thai=_limit_text(final_status, 32) or "Đã xuất",
                    assigned_at=(
                        _dt_from_iso(_row_text(loc, "ngay_cap_nhat"))
                        or _dt_from_iso(_row_text(ck, "ngay_cap_nhat"))
                        or receipt_dt
                        or now
                    ),
                    updated_at=(
                        _dt_from_iso(_row_text(loc, "ngay_cap_nhat"))
                        or _dt_from_iso(_row_text(ck, "ngay_cap_nhat"))
                        or receipt_dt
                        or now
                    ),
                )
            )
            stats["location_assignments_created"] += 1

        if issue_date is None:
            fallback_dt = (
                _dt_from_iso(_row_text(loc, "ngay_cap_nhat"))
                or _dt_from_iso(_row_text(ck, "ngay_cap_nhat"))
                or receipt_dt
                or now
            )
            issue_date = fallback_dt.date()

        status = _issue_status(_row_text(iss, "status"))
        issue, created_issue = _issue_for_legacy_day(
            db,
            nhu_cau=nhu_cau,
            lot=lot,
            ngay_xuat=issue_date,
            status=status,
        )
        if created_issue:
            stats["issues_created"] += 1
        existing_issue_line = (
            db.query(IssueLine)
            .filter(IssueLine.issue_id == issue.id)
            .filter(IssueLine.ma_cay == ma_cay)
            .first()
        )
        if not existing_issue_line:
            db.add(
                IssueLine(
                    issue_id=issue.id,
                    ma_cay=ma_cay,
                    so_luong_xuat=_as_float(_row_value(iss, "so_luong_xuat")) or actual_yards,
                    vi_tri=vi_tri[:16] if vi_tri else None,
                )
            )
            db.flush()
            stats["issue_lines_created"] += 1

        if ret is not None:
            issue_line = db.query(IssueLine).filter(IssueLine.ma_cay == ma_cay).order_by(IssueLine.id.desc()).first()
            ngay_tai_nhap = _parse_ngay_xuat(_row_text(ret, "ngay_tai_nhap"))
            if issue_line and ngay_tai_nhap:
                existing_ret = db.query(ReturnEvent).filter(ReturnEvent.issue_line_id == issue_line.id).first()
                if not existing_ret:
                    db.add(
                        ReturnEvent(
                            issue_line_id=issue_line.id,
                            ma_cay=ma_cay,
                            ngay_tai_nhap=ngay_tai_nhap,
                            yds_du=_as_float(_row_value(ret, "so_yds_du")),
                            status=_limit_text(_row_text(ret, "trang_thai"), 64) or "Tái nhập kho",
                            nhu_cau_moi=_limit_text(_row_text(ret, "nhu_cau_moi"), 64),
                            lot_moi=None,
                            vi_tri_moi=_limit_text(_row_text(ret, "vi_tri_moi"), 16),
                            note=_limit_text(_row_text(ret, "ghi_chu"), 500),
                        )
                    )
                    stats["return_events_created"] += 1

    return stats


def backfill_exported_issue_history(db: Session) -> dict[str, int]:
    """
    Ensure exported/non-stored rolls already present in Postgres appear in issue history.
    """
    stored_statuses = {"Đang lưu", "Dang luu", "Đang luu", "Dang lưu"}
    rows = (
        db.query(LocationAssignment)
        .outerjoin(IssueLine, IssueLine.ma_cay == LocationAssignment.ma_cay)
        .filter(IssueLine.id.is_(None))
        .filter(~LocationAssignment.trang_thai.in_(stored_statuses))
        .all()
    )

    issues_created = 0
    lines_created = 0
    for la in rows:
        if not la.ma_cay:
            continue

        receipt_pair = (
            db.query(ReceiptLine, Receipt)
            .join(Receipt, Receipt.id == ReceiptLine.receipt_id)
            .filter(ReceiptLine.ma_cay == la.ma_cay)
            .first()
        )
        receipt_date = receipt_pair[1].receipt_date if receipt_pair else None
        issue_date = receipt_date or (la.updated_at.date() if la.updated_at else None) or (la.assigned_at.date() if la.assigned_at else None)
        if issue_date is None:
            issue_date = datetime.now(timezone.utc).date()

        status = _issue_status(la.trang_thai)
        issue, created_issue = _issue_for_legacy_day(
            db,
            nhu_cau=la.nhu_cau,
            lot=la.lot,
            ngay_xuat=issue_date,
            status=status,
        )
        if created_issue:
            issues_created += 1

        sc = (
            db.query(StockCheck)
            .filter(StockCheck.ma_cay == la.ma_cay)
            .filter(StockCheck.nhu_cau == la.nhu_cau)
            .filter(StockCheck.lot == la.lot)
            .first()
        )
        db.add(
            IssueLine(
                issue_id=issue.id,
                ma_cay=la.ma_cay,
                so_luong_xuat=(sc.actual_yards if sc and sc.actual_yards is not None else (sc.expected_yards if sc else None)),
                vi_tri=la.vi_tri[:16] if la.vi_tri else None,
            )
        )
        lines_created += 1

    return {
        "backfill_issues_created": issues_created,
        "backfill_issue_lines_created": lines_created,
    }


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
            ma = str(_mapping_value(r, "ma cay") or "").strip()
            if ma and ma in only_ma_cays:
                filtered.append(r)
        excel_rows = filtered

    # Group rows by "Ngày nhập hàng" (fallback "Ngày nhập"). Each group becomes 1 synthetic receipt.
    groups: dict[str, list[dict[str, object]]] = {}
    for r in excel_rows:
        ma_cay = str(_mapping_value(r, "ma cay") or "").strip()
        if not ma_cay:
            continue
        d0 = _date_from_any(str(_mapping_value(r, "ngay nhap hang") or "")) or _date_from_any(
            str(_mapping_value(r, "ngay nhap") or "")
        )
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
            ma = str(_mapping_value(r, "ma cay") or "").strip()
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
            ma_cay = str(_mapping_value(r, "ma cay") or "").strip()
            if not ma_cay or ma_cay in existing_ma:
                continue

            nhu_cau = _mapping_text(r, "nhu cau")
            lot = _mapping_text(r, "lot")
            anh_mau = _mapping_text(r, "anh mau")
            if anh_mau:
                anh_mau = _format_code(anh_mau) or anh_mau

            yards = _as_float(_mapping_value(r, "so luong"))
            art = _format_code(_mapping_value(r, "ma art"))

            line = ReceiptLine(
                receipt_id=receipt.id,
                roll_id=roll_id_by_ma.get(ma_cay),
                ma_cay=ma_cay,
                nhu_cau=_limit_text(nhu_cau, 64),
                lot=_limit_text(lot, 64),
                anh_mau=_limit_text(anh_mau, 64) or "CHUNG",
                model=None,
                art=_limit_text(art, 64),
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
            nhu_cau = _mapping_text(r, "nhu cau")
            lot = _mapping_text(r, "lot")
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

            customer = _format_code(_mapping_value(r, "customer"))
            tag.ngay_nhap_hang = receipt_date  # type: ignore[assignment]
            tag.nhu_cau = nhu_cau  # type: ignore[assignment]
            tag.lot = lot  # type: ignore[assignment]
            tag.ma_hang = _extract_ma_hang(nhu_cau)  # type: ignore[assignment]
            tag.customer = customer  # type: ignore[assignment]
            tag.nha_cung_cap = customer  # type: ignore[assignment]
            tag.khach_hang = "DECATHLON"  # type: ignore[assignment]
            tag.ngay_xuat = _parse_ngay_xuat(str(_mapping_value(r, "ngay xuat") or ""))  # type: ignore[assignment]

            tag.loai_vai = _format_code(_mapping_value(r, "ten art"))  # type: ignore[assignment]
            tag.ma_art = _format_code(_mapping_value(r, "ma art"))  # type: ignore[assignment]
            tag.mau_vai = _format_code(_mapping_value(r, "ten mau"))  # type: ignore[assignment]
            tag.ma_mau = _format_code(_mapping_value(r, "ma mau"))  # type: ignore[assignment]
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
    p.add_argument(
        "--import-missing-history",
        action="store_true",
        help="Import legacy ma_cay not present in Postgres as historical exported rolls.",
    )
    p.add_argument(
        "--history-limit",
        type=int,
        default=0,
        help="Optional cap for --import-missing-history (0 = no cap).",
    )
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
        if args.import_missing_history:
            stats.update(
                import_missing_legacy_history(
                    db,
                    wms_db_path=args.wms_db,
                    limit=(args.history_limit or None),
                )
            )
            stats.update(backfill_exported_issue_history(db))
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
