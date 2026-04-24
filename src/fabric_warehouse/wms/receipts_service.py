from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_roll import FabricRoll
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.wms.excel_import import ParsedReceipt, parse_receipt_excel


def _extract_ma_hang(nhu_cau: str | None) -> str | None:
    if not nhu_cau:
        return None
    import re

    m = re.search(r"(\d{6})", nhu_cau)
    return m.group(1) if m else None


def _format_code(val: object) -> str | None:
    if val is None:
        return None
    try:
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
    except Exception:
        pass
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def _parse_ngay_xuat(raw: dict[str, Any]) -> date | None:
    import re

    v = raw.get("Ngày xuất") or raw.get("Ngay xuat") or raw.get("Ngay xuất")
    if not v:
        return None
    s = str(v).strip()
    m = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", s)
    if not m:
        return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(yy, mm, dd)
    except Exception:
        return None


def import_receipt_from_excel(
    db: Session,
    *,
    content: bytes,
    source_filename: str,
) -> tuple[Receipt, list[str]]:
    parsed: ParsedReceipt = parse_receipt_excel(content, source_filename=source_filename)
    rows_to_import = list(parsed.rows)

    file_ma_cays = [r["ma_cay"] for r in rows_to_import if r.get("ma_cay")]
    duplicate_ma_cays: set[str] = set()
    if file_ma_cays:
        existing_line_rows = (
            db.query(ReceiptLine.ma_cay, ReceiptLine.receipt_id)
            .filter(ReceiptLine.ma_cay.in_(file_ma_cays))
            .all()
        )
        existing_receipt_by_ma_cay = {r[0]: r[1] for r in existing_line_rows}
        duplicate_ma_cays = set(existing_receipt_by_ma_cay)
        if duplicate_ma_cays:
            max_show = 10
            shown: list[str] = []
            for ma_cay in file_ma_cays:
                receipt_id = existing_receipt_by_ma_cay.get(ma_cay)
                if receipt_id is None:
                    continue
                shown.append(f"{ma_cay} (phiếu #{receipt_id})")
                if len(shown) >= max_show:
                    break
            more = len(duplicate_ma_cays) - len(shown)
            more_text = f" ... và {more} Mã cây khác" if more > 0 else ""
            parsed.warnings.append(
                "Bỏ qua "
                + str(len(duplicate_ma_cays))
                + " Mã cây đã tồn tại: "
                + "; ".join(shown)
                + more_text
                + "."
            )
            rows_to_import = [r for r in rows_to_import if r.get("ma_cay") not in duplicate_ma_cays]

    if parsed.rows and not rows_to_import:
        raise ValueError("Không có Mã cây mới để import; tất cả Mã cây trong file đã tồn tại.")

    # Pre-check hanging tag uniqueness before writing anything so we can either:
    # - treat it as a re-import (return old receipt), or
    # - import only new tags and skip duplicates with a warning.
    preview_ids: list[str] = []
    duplicate_tag_ids: set[str] = set()
    seen_keys: set[tuple[str | None, str | None]] = set()
    for row in rows_to_import:
        nhu_cau = row.get("nhu_cau")
        lot = row.get("lot")
        if not lot:
            continue
        key = (nhu_cau, lot)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        preview_ids.append(
            f"{nhu_cau or ''}-{lot}-{parsed.receipt_date.isoformat() if parsed.receipt_date else ''}"
        )

    if preview_ids:
        existing = (
            db.query(HangingTag.id_bang_treo, HangingTag.receipt_id)
            .filter(HangingTag.id_bang_treo.in_(preview_ids))
            .all()
        )
        if existing:
            file_ma_cays = {r["ma_cay"] for r in parsed.rows if r.get("ma_cay")}
            existing_by_id = {t[0]: t[1] for t in existing}
            receipt_ids = sorted({rid for rid in existing_by_id.values()})

            # If everything already exists and belongs to a single receipt, treat this as a re-import.
            if len(receipt_ids) == 1 and len(existing_by_id) == len(preview_ids):
                existing_receipt_id = receipt_ids[0]
                existing_ma_cays = {
                    r[0]
                    for r in db.query(ReceiptLine.ma_cay).filter(ReceiptLine.receipt_id == existing_receipt_id).all()
                }
                # Only auto-short-circuit if the file doesn't introduce any new "Mã cây".
                if file_ma_cays.issubset(existing_ma_cays):
                    existing_receipt = db.query(Receipt).filter(Receipt.id == existing_receipt_id).first()
                    if existing_receipt:
                        parsed.warnings.append(
                            f"File này đã được import trước đó (phiếu #{existing_receipt.id}). Hiển thị lại phiếu cũ."
                        )
                        return existing_receipt, parsed.warnings
                else:
                    parsed.warnings.append(
                        f"File có thêm Mã cây mới so với phiếu #{existing_receipt_id}; sẽ import phiếu mới và bỏ qua bảng treo trùng."
                    )

            # Import only new tags, skip duplicates (id_bang_treo is globally unique).
            duplicate_tag_ids = {tid for tid in preview_ids if tid in existing_by_id}
            if duplicate_tag_ids:
                max_show = 10
                shown: list[str] = []
                for tid in preview_ids:
                    rid = existing_by_id.get(tid)
                    if rid is None:
                        continue
                    shown.append(f"{tid} (phiếu #{rid})")
                    if len(shown) >= max_show:
                        break
                more = len(duplicate_tag_ids) - len(shown)
                more_text = f" ... và {more} bảng treo khác" if more > 0 else ""
                parsed.warnings.append(
                    "Bỏ qua "
                    + str(len(duplicate_tag_ids))
                    + " bảng treo đã tồn tại: "
                    + "; ".join(shown)
                    + more_text
                    + "."
                )

    receipt = Receipt(source_filename=parsed.source_filename, receipt_date=parsed.receipt_date)
    db.add(receipt)
    db.flush()  # assign receipt.id

    ma_cays: list[str] = [r["ma_cay"] for r in rows_to_import]
    if ma_cays:
        stmt = (
            pg_insert(FabricRoll.__table__)
            .values([{"ma_cay": mc} for mc in ma_cays])
            .on_conflict_do_nothing(index_elements=["ma_cay"])
        )
        db.execute(stmt)
        db.flush()

    rolls = (
        db.query(FabricRoll)
        .filter(FabricRoll.ma_cay.in_(ma_cays))
        .all()
    )
    roll_id_by_ma_cay = {r.ma_cay: r.id for r in rolls}

    line_values: list[dict[str, object]] = []
    for row in rows_to_import:
        raw_data: dict[str, Any] = row.get("raw_data") or {}
        ma_cay = row["ma_cay"]
        line_values.append(
            {
                "receipt_id": receipt.id,
                "roll_id": roll_id_by_ma_cay.get(ma_cay),
                "ma_cay": ma_cay,
                "nhu_cau": row.get("nhu_cau"),
                "lot": row.get("lot"),
                "anh_mau": row.get("anh_mau") or "CHUNG",
                "model": row.get("model"),
                "art": row.get("art"),
                "yards": row.get("yards"),
                "raw_data": raw_data,
            }
        )

    if line_values:
        stmt = pg_insert(ReceiptLine.__table__).values(line_values).on_conflict_do_nothing(
            index_elements=["ma_cay"]
        )
        db.execute(stmt)
        db.flush()

    # Build "bảng treo" (hanging tag) per (nhu_cau, lot, receipt_date) similar to legacy table_data.
    by_key: dict[tuple[str | None, str | None], dict[str, object]] = {}
    for row in rows_to_import:
        nhu_cau = row.get("nhu_cau")
        lot = row.get("lot")
        if not lot:
            continue
        key = (nhu_cau, lot)
        if key in by_key:
            continue
        raw = row.get("raw_data") or {}
        by_key[key] = {
            "nhu_cau": nhu_cau,
            "lot": lot,
            "ma_art": _format_code(row.get("art")),
            "ma_mau": _format_code(raw.get("Mã Màu") or raw.get("Ma Mau") or raw.get("Ma Màu")),
            "loai_vai": _format_code(raw.get("Tên Art") or raw.get("Ten Art")),
            "mau_vai": _format_code(raw.get("Tên Màu") or raw.get("Ten Mau") or raw.get("Ten Màu")),
            "customer": _format_code(raw.get("Customer")) or None,
            "ngay_xuat": _parse_ngay_xuat(raw),
        }

    tags: list[HangingTag] = []
    for (nhu_cau, lot), info in by_key.items():
        ngay_nhap = receipt.receipt_date
        id_bang_treo = f"{nhu_cau or ''}-{lot}-{ngay_nhap.isoformat() if ngay_nhap else ''}"
        if id_bang_treo in duplicate_tag_ids:
            continue
        tags.append(
            HangingTag(
                receipt_id=receipt.id,
                id_bang_treo=id_bang_treo,
                ngay_nhap_hang=ngay_nhap,
                nhu_cau=nhu_cau,
                lot=lot,
                ma_hang=_extract_ma_hang(nhu_cau),
                customer=info.get("customer") or None,
                ngay_xuat=info.get("ngay_xuat") if isinstance(info.get("ngay_xuat"), date) else None,
                nha_cung_cap=info.get("customer") or None,
                khach_hang="DECATHLON",
                loai_vai=info.get("loai_vai") or None,
                ma_art=info.get("ma_art") or None,
                mau_vai=info.get("mau_vai") or None,
                ma_mau=info.get("ma_mau") or None,
                ket_qua_kiem_tra="OK",
            )
        )

    if tags:
        # Insert in bulk and skip duplicates at DB level (id_bang_treo is globally unique).
        values = [
            {
                "receipt_id": t.receipt_id,
                "id_bang_treo": t.id_bang_treo,
                "ngay_nhap_hang": t.ngay_nhap_hang,
                "nhu_cau": t.nhu_cau,
                "lot": t.lot,
                "ma_hang": t.ma_hang,
                "nha_cung_cap": t.nha_cung_cap,
                "khach_hang": t.khach_hang,
                "loai_vai": t.loai_vai,
                "ma_art": t.ma_art,
                "mau_vai": t.mau_vai,
                "ma_mau": t.ma_mau,
                "customer": t.customer,
                "ngay_xuat": t.ngay_xuat,
                "ket_qua_kiem_tra": t.ket_qua_kiem_tra,
            }
            for t in tags
        ]
        stmt = pg_insert(HangingTag.__table__).values(values).on_conflict_do_nothing(
            index_elements=["id_bang_treo"]
        )
        db.execute(stmt)
        db.flush()

    return receipt, parsed.warnings


def list_receipts(db: Session, *, limit: int = 50) -> Sequence[Receipt]:
    return db.query(Receipt).order_by(Receipt.id.desc()).limit(limit).all()


def get_receipt(db: Session, *, receipt_id: int) -> Receipt | None:
    return db.query(Receipt).filter(Receipt.id == receipt_id).first()


def get_receipt_lines(db: Session, *, receipt_id: int) -> list[ReceiptLine]:
    return (
        db.query(ReceiptLine)
        .filter(ReceiptLine.receipt_id == receipt_id)
        .order_by(ReceiptLine.id.asc())
        .all()
    )
