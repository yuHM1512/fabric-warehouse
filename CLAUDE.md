# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fabric Warehouse (WMS) — a warehouse management system for fabric/textile inventory. Rebuilt from a legacy Streamlit `wms.py` into a FastAPI + server-rendered HTML app backed by PostgreSQL.

**Stack:** FastAPI, Jinja2 + Tailwind (server-rendered), SQLAlchemy 2.0, Alembic, PostgreSQL 16, Docker, ReportLab (PDF), Pandas/openpyxl (Excel import).

## Dev Setup & Common Commands

All scripts assume PowerShell from the project root. `PYTHONPATH=src` is set by the scripts — do not run `uvicorn` or `alembic` directly without it.

```powershell
# 1. Start Postgres
docker compose up -d

# 2. Create venv & install deps (first time)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 3. Run migrations
.\scripts\alembic.ps1 upgrade head

# 4. Start dev server (hot reload)
.\scripts\dev.ps1
# App: http://localhost:8000
```

**Alembic (migrations):**
```powershell
.\scripts\alembic.ps1 upgrade head
.\scripts\alembic.ps1 revision --autogenerate -m "description"
.\scripts\alembic.ps1 downgrade -1
```

**Data import scripts:**
```powershell
# Import fabric norms from legacy SQLite
.\scripts\import_fabric_data.ps1

# Scrape fabric norms from fabric.hachiba.app
.\scripts\scrape_fabric_data.ps1 --start-page 0 --end-page 50

# Reset/seed WMS test data
.\.venv\Scripts\python.exe -m fabric_warehouse.scripts.reset_wms_test_data --yes --all
.\.venv\Scripts\python.exe -m fabric_warehouse.scripts.reset_wms_test_data --yes --ma-cay CAY001 --recreate --nhu-cau NC-TEST --lot LOT-TEST
```

## Architecture

### Request Flow

```
HTTP Request
  → login_guard middleware (checks session["ma_nv"])
  → SessionMiddleware (must be added AFTER login_guard in main.py)
  → /api/* → api/router.py (JSON, currently just /api/health)
  → /* → web/router.py (HTML responses, all WMS pages)
  → / → main.py (dashboard)
```

### Key Architectural Decisions

- **Middleware order matters:** `login_guard` is registered before `SessionMiddleware` so that `request.session` is available inside the guard. This is intentional — do not reorder.
- **`PYTHONPATH=src`**: The package `fabric_warehouse` lives under `src/`. All imports use `fabric_warehouse.*`. Static files and templates are referenced with `src/fabric_warehouse/web/...` paths relative to the project root (where `uvicorn` runs).
- **No ORM relationships**: Services query the DB directly using `Session.query()`. There are no SQLAlchemy `relationship()` declarations — cross-table joins are done explicitly in service functions.
- **Location format**: Warehouse positions are stored as `"{tang}.{line}.{pallet}"` strings (e.g., `"A.01.03"`). `tang_options`, `line_options`, `pallet_options` in `location_service.py` define valid values.

### Domain Model (core tables)

| Table | Purpose |
|-------|---------|
| `fabric_roll` | Individual fabric rolls (ma_cay = roll ID) |
| `receipt` / receipt lines | Inbound delivery records (imported from Excel) |
| `hanging_tag` | Physical hang tags printed per roll |
| `stock_check` | Inventory check records (expected vs actual yards) |
| `location_assignment` | Current warehouse location per roll (`trang_thai`: "Đang lưu" / "Đã xuất") |
| `issue` / `issue_line` | Outbound issue events (xuất kho) |
| `return_event` | Returns from production back to warehouse |
| `location_transfer_log` | Audit log for location moves |
| `demand_transfer_log` | Audit log for nhu_cau reassignments |
| `fabric_data` | Fabric norms/specs (imported from legacy DB or scraped) |
| `user` | Employees; login is by `ma_nv` (employee code), no password |

### Business Logic Layer (`src/fabric_warehouse/wms/`)

Each `*_service.py` file owns one domain:
- `receipts_service.py` — Excel import → receipt + roll creation
- `stock_check_service.py` — inventory check upsert logic
- `location_service.py` — assign/query warehouse positions
- `issue_service.py` — create outbound issues, list history
- `return_service.py` — process returns from production
- `tools_service.py` — trace timeline, demand transfer, location transfer
- `dashboard_service.py` — KPI aggregations for the dashboard
- `pallet_metrics.py` — pallet capacity KPIs and layout map
- `fabric_norms.py` — query `fabric_data` table
- `pdf.py` / `hanging_pdf.py` — ReportLab PDF generation

### Authentication

Session-cookie auth (`fw_session`). Login requires only `ma_nv` (employee code) — no password. The `login_guard` middleware redirects unauthenticated requests to `/rcp/login?next=<url>`. Paths exempt from auth: `/`, `/guide`, `/wms`, `/rcp/login`, `/rcp/logout`, `/static/*`, `/api/*`, `/docs`.

## Environment Variables (`.env`)

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/fabric_warehouse
SECRET_KEY=<random string>
FABRIC_DB_PATH=<path to legacy fabric.db>   # for import_fabric_data script
HACHIBA_COOKIE=csrftoken=...; sessionid=... # for scrape_fabric_data (never commit)
```

Default `DATABASE_URL` in `config.py` matches `docker-compose.yml` — works out of the box for local dev.
