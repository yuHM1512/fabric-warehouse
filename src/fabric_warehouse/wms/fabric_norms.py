from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fabric_warehouse.db.models.fabric_data import FabricData


@dataclass(frozen=True)
class FabricNormRow:
    ma_model: str
    yrd_per_pallet: float | None
    ten_model: str | None


def search_norms_db(db: Session, query: str, *, limit: int = 50) -> list[FabricNormRow]:
    q = (query or "").strip()
    if not q:
        return []

    like = f"%{q}%"
    base = (
        db.query(FabricData)
        .filter(FabricData.yrd_per_pallet.isnot(None))
        .filter(FabricData.yrd_per_pallet > 0)
        .filter(or_(FabricData.ma_model == q, FabricData.ma_model.ilike(like)))
    )

    # numeric normalization
    try:
        q_int = str(int(float(q)))
        base = base.union_all(
            db.query(FabricData).filter(or_(FabricData.ma_model == q_int, FabricData.ma_model.ilike(f"%{q_int}%")))
        )
    except Exception:
        pass

    rows = base.order_by(FabricData.ma_model.asc()).limit(limit).all()
    return [
        FabricNormRow(
            ma_model=r.ma_model,
            yrd_per_pallet=float(r.yrd_per_pallet) if r.yrd_per_pallet is not None else None,
            ten_model=r.ten_model,
        )
        for r in rows
    ]


def list_ma_models(db: Session, *, limit: int = 5000) -> list[str]:
    rows = (
        db.query(FabricData.ma_model)
        .filter(FabricData.yrd_per_pallet.isnot(None))
        .filter(FabricData.yrd_per_pallet > 0)
        .filter(FabricData.ma_model.isnot(None))
        .distinct()
        .order_by(FabricData.ma_model.asc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def list_norm_rows(
    db: Session,
    *,
    ma_model: str | None,
    page: int,
    page_size: int,
) -> list[FabricNormRow]:
    page = max(1, int(page))
    page_size = min(500, max(10, int(page_size)))

    q = (
        db.query(FabricData)
        .filter(FabricData.yrd_per_pallet.isnot(None))
        .filter(FabricData.yrd_per_pallet > 0)
        .order_by(FabricData.ma_model.asc())
    )
    if ma_model:
        q = q.filter(FabricData.ma_model == ma_model)

    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return [
        FabricNormRow(
            ma_model=r.ma_model,
            yrd_per_pallet=float(r.yrd_per_pallet) if r.yrd_per_pallet is not None else None,
            ten_model=r.ten_model,
        )
        for r in rows
    ]
