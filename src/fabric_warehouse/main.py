from __future__ import annotations

from datetime import date, timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import quote

from fabric_warehouse.api.router import router as api_router
from fabric_warehouse.config import settings
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.session import get_db
from fabric_warehouse.wms.dashboard_service import compute_age_split_for_stored, list_in_out_by_day
from fabric_warehouse.wms.pallet_metrics import build_pallet_layout, compute_pallet_kpis
from fabric_warehouse.web.router import router as web_router
from fabric_warehouse.web.jinja_filters import fmt_gmt7

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api")
app.include_router(web_router)

app.mount("/static", StaticFiles(directory="src/fabric_warehouse/web/static"), name="static")
templates = Jinja2Templates(directory="src/fabric_warehouse/web/templates")
templates.env.filters["gmt7"] = fmt_gmt7


@app.middleware("http")
async def login_guard(request: Request, call_next):
    path = request.url.path or "/"
    allow_prefixes = (
        "/static/",
        "/api/",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    allow_exact = {
        "/",
        "/guide",
        "/wms",
        "/favicon.ico",
        "/rcp/login",
        "/rcp/logout",
    }

    if path in allow_exact or any(path.startswith(p) for p in allow_prefixes):
        return await call_next(request)

    if not (request.session or {}).get("ma_nv"):
        next_url = path
        if request.url.query:
            next_url = next_url + "?" + str(request.url.query)
        return RedirectResponse(url=f"/rcp/login?next={quote(next_url)}", status_code=307)

    return await call_next(request)


# Must be added AFTER the login_guard so request.session is available inside it.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="fw_session",
    https_only=False,
    same_site="lax",
    max_age=60 * 60 * 24 * 365,
)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not (request.session or {}).get("ma_nv"):
        next_url = str(request.url.path)
        if request.url.query:
            next_url = next_url + "?" + str(request.url.query)
        return templates.TemplateResponse(
            request,
            "wms/login.html",
            {
                "title": "Đăng nhập",
                "app_name": settings.app_name,
                "next_url": next_url,
                "error": request.query_params.get("error") or "",
            },
        )

    tab = (request.query_params.get("tab") or "overview").strip() or "overview"

    def _parse_day(key: str) -> date | None:
        v = (request.query_params.get(key) or "").strip()
        if not v:
            return None
        try:
            return date.fromisoformat(v)
        except Exception:
            return None

    # Card: total rolls stored
    try:
        total_rolls_stored = (
            db.query(LocationAssignment.id)
            .filter(LocationAssignment.trang_thai == "Đang lưu")
            .count()
        )
    except Exception:
        total_rolls_stored = 0

    # Card: pallet capacity KPI
    try:
        pallet_kpis = compute_pallet_kpis(db)
    except Exception:
        pallet_kpis = None

    # Layout: pallet map (only on demand)
    pallet_layout = None
    if tab == "layout":
        try:
            pallet_layout = build_pallet_layout(db)
        except Exception:
            pallet_layout = None

    # Chart: IN/OUT for last 7 days by default
    today = date.today()
    to_day = _parse_day("to") or today
    from_day = _parse_day("from") or (to_day - timedelta(days=7))
    if from_day > to_day:
        from_day, to_day = to_day, from_day

    try:
        in_out = list_in_out_by_day(db, from_day=from_day, to_day=to_day)
    except Exception:
        in_out = []

    # Skip Sundays for display
    in_out_display = [p for p in in_out if p.day.weekday() != 6]

    labels = [p.day.isoformat() for p in in_out_display]
    in_series = [round(p.in_m3, 4) for p in in_out_display]
    out_series = [round(p.out_m3, 4) for p in in_out_display]
    in_yds_series = [round(p.in_yds, 2) for p in in_out_display]
    out_yds_series = [round(p.out_yds, 2) for p in in_out_display]

    # Donut: age split for stored stock
    try:
        age_split = compute_age_split_for_stored(db)
    except Exception:
        age_split = None

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "Dashboard",
            "app_name": settings.app_name,
            "tab": tab,
            "total_rolls_stored": total_rolls_stored,
            "pallet_kpis": pallet_kpis,
            "pallet_layout": pallet_layout,
            "from_day": from_day,
            "to_day": to_day,
            "chart_labels": labels,
            "chart_in": in_series,
            "chart_out": out_series,
            "chart_in_yds": in_yds_series,
            "chart_out_yds": out_yds_series,
            "age_split": age_split,
        },
    )


@app.get("/wms")
def wms_legacy_redirect():
    return RedirectResponse(url="/guide", status_code=307)


@app.get("/guide", response_class=HTMLResponse)
def guide_home(request: Request):
    return templates.TemplateResponse(
        request,
        "guide/home.html",
        {"title": "Hướng dẫn", "app_name": settings.app_name},
    )
