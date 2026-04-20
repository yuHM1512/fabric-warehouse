from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fabric_warehouse.api.router import router as api_router
from fabric_warehouse.config import settings
from fabric_warehouse.db.session import get_db
from fabric_warehouse.db.models.fabric_roll import FabricRoll
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.db.models.location_assignment import LocationAssignment
from fabric_warehouse.db.models.receipt import Receipt
from fabric_warehouse.web.router import router as web_router

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api")
app.include_router(web_router)

app.mount("/static", StaticFiles(directory="src/fabric_warehouse/web/static"), name="static")
templates = Jinja2Templates(directory="src/fabric_warehouse/web/templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": settings.app_name, "app_name": settings.app_name},
    )


@app.get("/wms", response_class=HTMLResponse)
def wms_home(request: Request, db: Session = Depends(get_db)):
    try:
        receipts = db.query(Receipt.id).count()
    except Exception:
        receipts = 0
    try:
        hanging_tags = db.query(HangingTag.id).count()
    except Exception:
        hanging_tags = 0
    try:
        fabric_rolls = db.query(FabricRoll.id).count()
    except Exception:
        fabric_rolls = 0
    try:
        stored_rolls = (
            db.query(LocationAssignment.id)
            .filter(LocationAssignment.trang_thai == "Đang lưu")
            .count()
        )
    except Exception:
        stored_rolls = 0

    return templates.TemplateResponse(
        request,
        "wms/home.html",
        {
            "title": "WMS",
            "app_name": settings.app_name,
            "stats": {
                "receipts": receipts,
                "hanging_tags": hanging_tags,
                "fabric_rolls": fabric_rolls,
                "stored_rolls": stored_rolls,
            },
        },
    )
