# Fabric Warehouse (WMS)

Rebuild of the legacy Streamlit `wms.py` into:
- Backend: FastAPI
- UI: Server-rendered HTML + Tailwind (replace templates as you finalize UI)
- DB: PostgreSQL

## Dev quickstart (Windows PowerShell)

1) Create `.env` (see `.env.example`)
2) Start Postgres:
   - `docker compose up -d`
3) Install deps:
   - `python -m venv .venv`
   - `.\.venv\Scripts\pip install -r requirements.txt`
4) Run app:
   - `.\scripts\dev.ps1`

Open:
- `http://localhost:8000/wms/receipts` (import Excel -> download PDF)

## Migrations

- Initialize DB schema:
  - `.\scripts\alembic.ps1 upgrade head`

## Fabric norms (fabric_data)

- Import from legacy `fabric.db` into Postgres table `fabric_data`:
  - (Ensure `.env` has `FABRIC_DB_PATH=...`)
  - `.\scripts\import_fabric_data.ps1`

- Or scrape from `fabric.hachiba.app` directly into Postgres `fabric_data`:
  - Set cookie env var (do NOT commit it):
    - `$env:HACHIBA_COOKIE='csrftoken=...; sessionid=...'`
  - Run:
    - `.\scripts\scrape_fabric_data.ps1 --start-page 0 --end-page 50`
