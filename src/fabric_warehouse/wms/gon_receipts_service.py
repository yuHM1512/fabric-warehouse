from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from fabric_warehouse.db.models.gon_receipt import GonReceipt


def _clean_text(value: object, max_len: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_len]


def _parse_date(value: object, *, required: bool = False) -> date | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError("Ngày nhập là bắt buộc.")
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Ngày nhập không hợp lệ.") from exc


def create_gon_receipt(
    db: Session,
    *,
    nha_cung_cap: object,
    ten_gon: object,
    quy_cach: object,
    ma_hang: object,
    mua: object,
    ngay_nhap: object,
) -> GonReceipt:
    item_name = _clean_text(ten_gon, 255)
    if not item_name:
        raise ValueError("Tên gòn là bắt buộc.")

    item = GonReceipt(
        nha_cung_cap=_clean_text(nha_cung_cap, 255),
        ten_gon=item_name,
        quy_cach=_clean_text(quy_cach, 255),
        ma_hang=_clean_text(ma_hang, 64),
        mua=_clean_text(mua, 64),
        ngay_nhap=_parse_date(ngay_nhap),
    )
    db.add(item)
    db.flush()
    return item


def update_gon_receipt_date(
    db: Session,
    *,
    item_id: int,
    ngay_nhap: object,
) -> GonReceipt | None:
    item = db.query(GonReceipt).filter(GonReceipt.id == item_id).first()
    if not item:
        return None
    item.ngay_nhap = _parse_date(ngay_nhap, required=True)
    db.add(item)
    db.flush()
    return item


def list_gon_receipts(db: Session, *, limit: int = 200) -> Sequence[GonReceipt]:
    return db.query(GonReceipt).order_by(GonReceipt.id.desc()).limit(limit).all()


def list_gon_receipts_by_ids(db: Session, *, ids: list[int]) -> list[GonReceipt]:
    if not ids:
        return []
    return db.query(GonReceipt).filter(GonReceipt.id.in_(ids)).order_by(GonReceipt.id.asc()).all()
