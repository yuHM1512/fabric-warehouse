from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine
from fabric_warehouse.wms.receipts_service import _extract_ma_hang, _format_code

STORED_STATUSES = ("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")


@dataclass(frozen=True)
class PalletHangingRow:
    vi_tri: str
    roll_count: int
    lots: list[str]
    nhu_caus: list[str]
    loai_vais: list[str]


def _parse_ngay_xuat(raw: dict) -> object | None:
    """
    Raw 'Ngày xuất' often looks like '10:07 12/12/2025'.
    Store only the date part.
    """
    import re
    from datetime import date as _date

    v = raw.get("Ngày xuất") or raw.get("Ngay xuat") or raw.get("Ngay xuất")
    if not v:
        return None
    s = str(v).strip()
    m = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", s)
    if not m:
        return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return _date(yy, mm, dd)
    except Exception:
        return None


def _build_tag_values(
    *,
    receipt: Receipt,
    line: ReceiptLine,
) -> dict[str, object]:
    raw = line.raw_data or {}
    ngay_nhap = receipt.receipt_date
    id_bang_treo = f"{(line.nhu_cau or '')}-{(line.lot or '')}-{ngay_nhap.isoformat() if ngay_nhap else ''}"
    return {
        "receipt_id": receipt.id,
        "id_bang_treo": id_bang_treo,
        "ngay_nhap_hang": ngay_nhap,
        "nhu_cau": line.nhu_cau,
        "lot": line.lot,
        "ma_hang": _extract_ma_hang(line.nhu_cau),
        "customer": _format_code(raw.get("Customer")) or None,
        "ngay_xuat": _parse_ngay_xuat(raw),
        "nha_cung_cap": _format_code(raw.get("Customer")) or None,
        "khach_hang": "DECATHLON",
        "loai_vai": _format_code(raw.get("Tên Art") or raw.get("Ten Art")),
        "ma_art": _format_code(line.art),
        "mau_vai": _format_code(raw.get("Tên Màu") or raw.get("Ten Mau") or raw.get("Ten Màu")),
        "ma_mau": _format_code(raw.get("Mã Màu") or raw.get("Ma Mau") or raw.get("Ma Màu")),
        "ket_qua_kiem_tra": "OK",
    }


def backfill_hanging_tags(db: Session, *, receipt_limit: int = 200) -> int:
    """
    Create missing hanging tags for receipts imported before hanging_tags existed.
    A hanging tag is created per unique (nhu_cau, lot, receipt_date) inside a receipt.
    """
    receipts = db.query(Receipt).order_by(Receipt.id.desc()).limit(receipt_limit).all()
    if not receipts:
        return 0

    created = 0
    for receipt in receipts:
        has_any = db.query(HangingTag.id).filter(HangingTag.receipt_id == receipt.id).first()
        if has_any:
            continue

        lines: list[ReceiptLine] = (
            db.query(ReceiptLine)
            .filter(ReceiptLine.receipt_id == receipt.id)
            .order_by(ReceiptLine.id.asc())
            .all()
        )
        if not lines:
            continue

        # pick the first line per (nhu_cau, lot) to represent the tag
        seen: set[tuple[str | None, str | None]] = set()
        values: list[dict[str, object]] = []
        for ln in lines:
            if not ln.lot:
                continue
            key = (ln.nhu_cau, ln.lot)
            if key in seen:
                continue
            seen.add(key)
            values.append(_build_tag_values(receipt=receipt, line=ln))

        if not values:
            continue

        stmt = pg_insert(HangingTag.__table__).values(values).on_conflict_do_nothing(
            index_elements=["id_bang_treo"]
        )
        res = db.execute(stmt)
        # rowcount may be -1 depending on driver; approximate using len(values)
        created += (res.rowcount if getattr(res, "rowcount", None) not in (None, -1) else len(values))

    return created


def fill_missing_hanging_fields(db: Session, *, tag_ids: list[int]) -> int:
    """
    Fill missing `customer` / `ngay_xuat` for existing hanging_tags using receipt_lines.raw_data.
    Does NOT overwrite existing non-empty values.
    """
    if not tag_ids:
        return 0

    tags: list[HangingTag] = db.query(HangingTag).filter(HangingTag.id.in_(tag_ids)).all()
    if not tags:
        return 0

    receipt_ids = sorted({t.receipt_id for t in tags})
    lines: list[ReceiptLine] = (
        db.query(ReceiptLine)
        .filter(ReceiptLine.receipt_id.in_(receipt_ids))
        .order_by(ReceiptLine.id.asc())
        .all()
    )
    first_line_by_key: dict[tuple[int, str | None, str | None], ReceiptLine] = {}
    for ln in lines:
        if not ln.lot:
            continue
        key = (ln.receipt_id, ln.nhu_cau, ln.lot)
        if key not in first_line_by_key:
            first_line_by_key[key] = ln

    changed = 0
    for t in tags:
        key = (t.receipt_id, t.nhu_cau, t.lot)
        ln = first_line_by_key.get(key)
        if not ln:
            continue
        raw = ln.raw_data or {}

        updated = False
        if not (t.customer and t.customer.strip()):
            cust = _format_code(raw.get("Customer"))
            if cust:
                t.customer = cust
                if not (t.nha_cung_cap and t.nha_cung_cap.strip()):
                    t.nha_cung_cap = cust
                updated = True

        if t.ngay_xuat is None:
            nx = _parse_ngay_xuat(raw)
            if nx:
                t.ngay_xuat = nx  # type: ignore[assignment]
                updated = True

        if updated:
            db.add(t)
            changed += 1

    return changed


def _uniq(values: Iterable[object]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _uniq_join(values: Iterable[object], sep: str = " / ") -> str:
    return sep.join(_uniq(values))


def _first_nonempty(values: Iterable[object], default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _pallet_assignments(db: Session, *, vi_tris: list[str] | None = None) -> list[LocationAssignment]:
    q = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.trang_thai.in_(STORED_STATUSES))
        .filter(LocationAssignment.vi_tri.isnot(None))
    )
    if vi_tris:
        q = q.filter(LocationAssignment.vi_tri.in_(vi_tris))
    return q.order_by(LocationAssignment.vi_tri.asc(), LocationAssignment.lot.asc(), LocationAssignment.ma_cay.asc()).all()


def _hanging_tags_for_assignments(db: Session, assignments: list[LocationAssignment]) -> dict[tuple[str, str], HangingTag]:
    keys = sorted({(a.nhu_cau, a.lot) for a in assignments if a.nhu_cau and a.lot})
    if not keys:
        return {}

    nhu_caus = sorted({nc for nc, _lot in keys})
    lots = sorted({lot for _nc, lot in keys})
    tags = (
        db.query(HangingTag)
        .filter(HangingTag.nhu_cau.in_(nhu_caus))
        .filter(HangingTag.lot.in_(lots))
        .order_by(HangingTag.id.asc())
        .all()
    )
    out: dict[tuple[str, str], HangingTag] = {}
    wanted = set(keys)
    for tag in tags:
        key = (tag.nhu_cau or "", tag.lot or "")
        if key not in wanted or key in out:
            continue
        out[key] = tag
    return out


def list_pallet_hanging_rows(db: Session) -> list[PalletHangingRow]:
    assignments = _pallet_assignments(db)
    if not assignments:
        return []
    tag_by_key = _hanging_tags_for_assignments(db, assignments)

    grouped: dict[str, list[LocationAssignment]] = {}
    for assignment in assignments:
        vi_tri = (assignment.vi_tri or "").strip()
        if not vi_tri:
            continue
        grouped.setdefault(vi_tri, []).append(assignment)

    rows: list[PalletHangingRow] = []
    for vi_tri, items in grouped.items():
        tags = [tag_by_key[(a.nhu_cau, a.lot)] for a in items if (a.nhu_cau, a.lot) in tag_by_key]
        rows.append(
            PalletHangingRow(
                vi_tri=vi_tri,
                roll_count=len(items),
                lots=_uniq(a.lot for a in items),
                nhu_caus=_uniq(a.nhu_cau for a in items),
                loai_vais=_uniq(tag.loai_vai for tag in tags),
            )
        )
    return rows


def build_pallet_hanging_tags(db: Session, *, vi_tris: list[str] | None = None) -> list[SimpleNamespace]:
    assignments = _pallet_assignments(db, vi_tris=vi_tris)
    if not assignments:
        return []
    tag_by_key = _hanging_tags_for_assignments(db, assignments)

    grouped: dict[str, list[LocationAssignment]] = {}
    for assignment in assignments:
        vi_tri = (assignment.vi_tri or "").strip()
        if not vi_tri:
            continue
        grouped.setdefault(vi_tri, []).append(assignment)

    out: list[SimpleNamespace] = []
    for vi_tri, items in grouped.items():
        tags = [tag_by_key[(a.nhu_cau, a.lot)] for a in items if (a.nhu_cau, a.lot) in tag_by_key]
        lots = _uniq(a.lot for a in items)
        out.append(
            SimpleNamespace(
                khach_hang=_first_nonempty((tag.khach_hang for tag in tags), default="DECATHLON"),
                nha_cung_cap=_uniq_join(tag.nha_cung_cap for tag in tags),
                customer=_uniq_join(tag.customer for tag in tags),
                ngay_nhap_hang=min((tag.ngay_nhap_hang for tag in tags if tag.ngay_nhap_hang), default=None),
                ma_hang=vi_tri,
                nhu_cau=_uniq_join(a.nhu_cau for a in items),
                loai_vai=_uniq_join(tag.loai_vai for tag in tags),
                ma_art=_uniq_join(tag.ma_art for tag in tags),
                mau_vai=_uniq_join(tag.mau_vai for tag in tags),
                ma_mau=_uniq_join(tag.ma_mau for tag in tags),
                lot=lots[0] if len(lots) == 1 else "",
                lot_lines=lots,
                ket_qua_kiem_tra="OK",
            )
        )
    return out
