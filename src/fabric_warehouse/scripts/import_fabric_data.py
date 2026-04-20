from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from fabric_warehouse.config import settings
from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.session import engine


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def load_from_sqlite(sqlite_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('SELECT * FROM fabric_table').fetchall()
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for r in rows:
        ma_model = (r.get("Mã Model") or r.get("Ma Model") or "").strip()
        if not ma_model:
            continue
        d = dict(r)
        out.append(
            {
                "ma_model": ma_model,
                "ten_model": (r.get("Tên Model") or r.get("Ten Model") or None),
                "ghi_chu": (r.get("Ghi chú") or r.get("Ghi chu") or None),
                "yrd_per_pallet": _to_float(r.get("YRD/Pallet")),
                "usd_per_yrd": _to_float(r.get("USD/YRD")),
                "raw_data": d,
            }
        )
    return out


def upsert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(FabricData.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ma_model"],
        set_={
            "ten_model": stmt.excluded.ten_model,
            "ghi_chu": stmt.excluded.ghi_chu,
            "yrd_per_pallet": stmt.excluded.yrd_per_pallet,
            "usd_per_yrd": stmt.excluded.usd_per_yrd,
            "raw_data": stmt.excluded.raw_data,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    with engine.begin() as conn:
        res = conn.execute(stmt)
    return int(res.rowcount or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Import fabric_table from sqlite into Postgres fabric_data")
    ap.add_argument("--sqlite", dest="sqlite_path", default=settings.fabric_db_path, help="Path to fabric.db")
    args = ap.parse_args()

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    rows = load_from_sqlite(sqlite_path)
    n = upsert_rows(rows)
    print(f"Upserted {n} rows into fabric_data from {sqlite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

