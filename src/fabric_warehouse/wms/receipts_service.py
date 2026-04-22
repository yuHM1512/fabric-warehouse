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

    receipt = Receipt(source_filename=parsed.source_filename, receipt_date=parsed.receipt_date)
    db.add(receipt)
    db.flush()  # assign receipt.id

    ma_cays: list[str] = [r["ma_cay"] for r in parsed.rows]
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

    lines: list[ReceiptLine] = []
    for row in parsed.rows:
        raw_data: dict[str, Any] = row.get("raw_data") or {}
        ma_cay = row["ma_cay"]
        line = ReceiptLine(
            receipt_id=receipt.id,
            roll_id=roll_id_by_ma_cay.get(ma_cay),
            ma_cay=ma_cay,
            nhu_cau=row.get("nhu_cau"),
            lot=row.get("lot"),
            anh_mau=(row.get("anh_mau") or "CHUNG"),
            model=row.get("model"),
            art=row.get("art"),
            yards=row.get("yards"),
            raw_data=raw_data,
        )
        lines.append(line)

    db.add_all(lines)
    db.flush()

    # Build "bảng treo" (hanging tag) per (nhu_cau, lot, receipt_date) similar to legacy table_data.
    by_key: dict[tuple[str | None, str | None], dict[str, object]] = {}
    for row in parsed.rows:
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
        # Parse "Ngày xuất" from raw row if present.
        raw0 = {}
        try:
            raw0 = (info.get("raw_data") if isinstance(info.get("raw_data"), dict) else {})  # type: ignore[assignment]
        except Exception:
            raw0 = {}
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
        # avoid duplicate tags when re-importing same file
        existing = {
            t[0]
            for t in db.query(HangingTag.id_bang_treo)
            .filter(HangingTag.receipt_id == receipt.id)
            .all()
        }
        tags = [t for t in tags if t.id_bang_treo not in existing]
        db.add_all(tags)
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
