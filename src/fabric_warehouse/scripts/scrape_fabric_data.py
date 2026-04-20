from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fabric_warehouse.db.models.fabric_data import FabricData
from fabric_warehouse.db.session import engine


@dataclass(frozen=True)
class ScrapeConfig:
    base_url: str
    start_page: int
    end_page_exclusive: int
    cookie: str
    sleep_seconds: float
    timeout_seconds: float


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


def _extract_table_rows(html: str) -> tuple[list[str], list[list[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table-model")
    if not table:
        return [], []

    header: list[str] = []
    thead = table.find("thead")
    if thead:
        header = [th.get_text(strip=True) for th in thead.find_all("th")]
    else:
        first_row = table.find("tr")
        if first_row:
            header = [td.get_text(strip=True) for td in first_row.find_all(["th", "td"])]

    body = table.find("tbody")
    trs = body.find_all("tr") if body else table.find_all("tr")[1:]

    rows: list[list[str]] = []
    for tr in trs:
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cols:
            rows.append(cols)
    return header, rows


def _map_rows(header: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    """
    Only keep basic columns like legacy sqlite table:
      '#', 'Mã Model', 'Tên Model', 'Ghi chú', 'YRD/Pallet', 'USD/YRD', 'Thao tác'
    """
    if not header or not rows:
        return []
    idx = {name: i for i, name in enumerate(header)}

    def get(col: str, r: list[str]) -> str | None:
        i = idx.get(col)
        if i is None or i >= len(r):
            return None
        v = (r[i] or "").strip()
        return v or None

    out: list[dict[str, Any]] = []
    for r in rows:
        ma_model = get("Mã Model", r)
        if not ma_model:
            continue
        out.append(
            {
                "ma_model": ma_model,
                "ten_model": get("Tên Model", r),
                "ghi_chu": get("Ghi chú", r),
                "yrd_per_pallet": _to_float(get("YRD/Pallet", r)),
                "usd_per_yrd": _to_float(get("USD/YRD", r)),
                # keep minimal raw_data
                "raw_data": {
                    "#": get("#", r),
                    "Mã Model": ma_model,
                    "Tên Model": get("Tên Model", r),
                    "Ghi chú": get("Ghi chú", r),
                    "YRD/Pallet": get("YRD/Pallet", r),
                    "USD/YRD": get("USD/YRD", r),
                    "Thao tác": get("Thao tác", r),
                },
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


def scrape_and_upsert(cfg: ScrapeConfig) -> None:
    session = requests.Session()
    session.headers.update(
        {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "vi,en-US;q=0.9,en;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "referer": cfg.base_url.split("?")[0],
            "cookie": cfg.cookie,
        }
    )

    total_upserted = 0
    for page in range(cfg.start_page, cfg.end_page_exclusive):
        url = cfg.base_url.format(page=page)
        resp = session.get(url, timeout=cfg.timeout_seconds)
        resp.raise_for_status()

        header, rows = _extract_table_rows(resp.text)
        mapped = _map_rows(header, rows)
        n = upsert_rows(mapped)
        total_upserted += n
        print(f"page {page}: rows={len(rows)} upserted={n}")

        if cfg.sleep_seconds:
            time.sleep(cfg.sleep_seconds)

    print(f"Done. Total upserted={total_upserted}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape fabric.hachiba.app and upsert into Postgres fabric_data")
    ap.add_argument(
        "--base-url",
        default="https://fabric.hachiba.app/model_fabric_list/?model_code=&&type=all&&page_number={page}",
    )
    ap.add_argument("--start-page", type=int, default=0)
    ap.add_argument("--end-page", type=int, default=50, help="Exclusive")
    ap.add_argument(
        "--cookie",
        required=True,
        help="Raw Cookie header string (do NOT commit; pass via env or CLI)",
    )
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    cfg = ScrapeConfig(
        base_url=args.base_url,
        start_page=args.start_page,
        end_page_exclusive=args.end_page,
        cookie=args.cookie,
        sleep_seconds=args.sleep,
        timeout_seconds=args.timeout,
    )
    scrape_and_upsert(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

