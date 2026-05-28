from __future__ import annotations

from io import BytesIO
from pathlib import Path

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from fabric_warehouse.db.session import get_db
from fabric_warehouse.wms.hanging_pdf import render_hanging_tag_pdf, render_merged_hanging_tag_pdf
from fabric_warehouse.wms.reports_service import (
    build_stock_export_excel,
    inbound_status_by_nhu_cau,
    list_active_inbound_nhu_cau_options,
    ton_kho_by_age_split,
    ton_kho_by_loai_vai,
    ton_kho_by_lot,
    ton_kho_by_mau_vai,
    ton_kho_by_nhu_cau,
)
from fabric_warehouse.wms.hanging_service import backfill_hanging_tags, fill_missing_hanging_fields
from fabric_warehouse.wms.gon_receipts_service import (
    create_gon_receipt,
    list_gon_receipts,
    list_gon_receipts_by_ids,
    update_gon_receipt_date,
)
from fabric_warehouse.wms.pdf import render_receipt_pdf
from fabric_warehouse.wms.receipts_service import (
    get_receipt,
    get_receipt_lines,
    import_receipt_from_excel,
    list_receipts,
)
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.wms.stock_check_service import (
    get_pallet_audit_session_detail,
    get_pallet_audit_rows,
    get_roll_rows,
    list_incomplete_lot_summaries,
    list_lot_options,
    list_nhu_cau_options,
    list_pallet_audit_sessions,
    save_pallet_audit,
    search_pallet_audit_lots,
    search_pallet_audit_rolls,
    upsert_stock_checks,
)
from fabric_warehouse.wms.gon_stock_service import (
    create_gon_stock_entry,
    create_gon_issue,
    create_gon_transfer,
    list_gon_block_rows,
    list_gon_issue_candidates,
    list_gon_issue_history,
    list_gon_issue_location_options,
    list_gon_issue_type_options,
    list_gon_type_options,
    list_recent_gon_stock_entries,
    list_gon_transfer_history,
)
from fabric_warehouse.wms.location_service import (
    assign_location,
    build_location_code,
    expanded_block_options,
    is_valid_location_parts,
    parse_location_code,
    line_options,
    list_anh_mau_options,
    list_lot_options_for_location,
    list_nhu_cau_options_for_location,
    list_rolls_for_location,
    pallet_options,
    pallet_options_by_line,
    tang_options,
    warehouse_area_options,
)
from fabric_warehouse.wms.issue_service import (
    count_issue_lines,
    create_issue,
    list_issue_candidates,
    list_issue_history,
    list_issue_lot_options,
    list_issue_nhu_cau_options,
)
from fabric_warehouse.wms.return_service import (
    create_return,
    list_return_candidates,
    list_return_history,
    list_pending_return_lot_options,
    list_pending_return_nhu_cau_options,
    list_pending_return_ten_art_options,
)
from fabric_warehouse.db.models.issue import IssueLine
from fabric_warehouse.wms.fabric_norms import list_ma_models, list_norm_rows, search_norms_db
from fabric_warehouse.wms.pallet_metrics import list_pallet_roll_rows
from fabric_warehouse.wms.tools_service import (
    build_trace_timeline,
    list_trace_lots,
    list_trace_ma_cays,
    transfer_demand,
    transfer_location,
)
from fabric_warehouse.web.jinja_filters import clean_note, fmt_date_dmy, fmt_gmt7
from fabric_warehouse.config import settings
from fabric_warehouse.db.models.user import User

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_DIR / "templates"

templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape=select_autoescape(["html", "xml"]),
    )
)
templates.env.filters["gmt7"] = fmt_gmt7
templates.env.filters["clean_note"] = clean_note
templates.env.filters["dmy"] = fmt_date_dmy

router = APIRouter()


def _safe_next_url(raw: str | None) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        return "/"
    if raw.startswith("//"):
        return "/"
    return raw


def _selected_nhu_caus(request: Request) -> list[str]:
    seen: list[str] = []
    for raw in request.query_params.getlist("nhu_cau"):
        value = (raw or "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _nhu_cau_query_string(values: list[str]) -> str:
    if not values:
        return ""
    return urlencode([("nhu_cau", value) for value in values], doseq=True)


@router.get("/rcp/login", response_class=HTMLResponse)
def rcp_login(request: Request):
    next_url = _safe_next_url(request.query_params.get("next"))
    error = (request.query_params.get("error") or "").strip()
    return templates.TemplateResponse(
        request,
        "wms/login.html",
        {
            "title": "Đăng nhập",
            "app_name": settings.app_name,
            "next_url": next_url,
            "error": error,
        },
    )


@router.post("/rcp/login")
async def rcp_login_post(
    request: Request,
    ma_nv: str = Form(...),
    db: Session = Depends(get_db),
):
    next_url = _safe_next_url(request.query_params.get("next"))
    code = (ma_nv or "").strip().upper()
    if not code:
        return HTMLResponse("Missing ma_nv", status_code=400)

    user = db.query(User).filter(User.ma_nv == code).first()
    if not user:
        return HTMLResponse("Invalid ma_nv", status_code=401)

    request.session["ma_nv"] = user.ma_nv
    request.session["ho_ten"] = user.ho_ten or ""
    return RedirectResponse(url=next_url, status_code=303)


@router.get("/rcp/logout")
def rcp_logout(request: Request):
    try:
        request.session.clear()
    except Exception:
        pass
    return RedirectResponse(url="/", status_code=303)


@router.get("/wms/receipts", response_class=HTMLResponse)
def receipts_home(request: Request, db: Session = Depends(get_db)):
    receipts = list_receipts(db, limit=50)
    gon_error: str | None = None
    try:
        gon_receipts = list_gon_receipts(db, limit=200)
    except ProgrammingError as e:
        gon_receipts = []
        gon_error = str(e.orig) if getattr(e, "orig", None) else str(e)
    return templates.TemplateResponse(
        request,
        "wms/receipts.html",
        {
            "title": "Phiếu nhập kho",
            "tab": "regular",
            "receipts": receipts,
            "gon_receipts": gon_receipts,
            "gon_error": gon_error,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.get("/wms/receipts/gon", response_class=HTMLResponse)
def gon_receipts_home(request: Request, db: Session = Depends(get_db)):
    receipts = list_receipts(db, limit=50)
    gon_error: str | None = None
    try:
        gon_receipts = list_gon_receipts(db, limit=200)
    except ProgrammingError as e:
        gon_receipts = []
        gon_error = str(e.orig) if getattr(e, "orig", None) else str(e)
    return templates.TemplateResponse(
        request,
        "wms/receipts.html",
        {
            "title": "Phiếu nhập kho",
            "tab": "gon",
            "receipts": receipts,
            "gon_receipts": gon_receipts,
            "gon_error": gon_error,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/wms/receipts/import", response_class=HTMLResponse)
async def receipts_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rá»—ng.")

    try:
        receipt, warnings = import_receipt_from_excel(
            db, content=content, source_filename=(file.filename or "upload.xlsx")
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    lines = get_receipt_lines(db, receipt_id=receipt.id)
    return templates.TemplateResponse(
        request,
        "wms/receipt_detail.html",
        {
            "title": f"Phiếu #{receipt.id}",
            "receipt": receipt,
            "lines": lines,
            "warnings": warnings,
        },
    )


@router.post("/wms/receipts/gon")
async def gon_receipts_create(
    nha_cung_cap: str | None = Form(default=None),
    ten_gon: str = Form(...),
    quy_cach: str | None = Form(default=None),
    ma_hang: str | None = Form(default=None),
    mua: str | None = Form(default=None),
    ngay_nhap: date | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        create_gon_receipt(
            db,
            nha_cung_cap=nha_cung_cap,
            ten_gon=ten_gon,
            quy_cach=quy_cach,
            ma_hang=ma_hang,
            mua=mua,
            ngay_nhap=ngay_nhap.isoformat() if ngay_nhap else None,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    return RedirectResponse(url="/wms/receipts/gon?saved=1", status_code=303)


@router.post("/wms/hanging/gon/{item_id}/edit-date")
def hanging_gon_edit_date(
    item_id: int,
    db: Session = Depends(get_db),
    ngay_nhap: date | None = Form(default=None),
):
    try:
        item = update_gon_receipt_date(
            db,
            item_id=item_id,
            ngay_nhap=ngay_nhap.isoformat() if ngay_nhap else None,
        )
        if not item:
            return JSONResponse({"ok": False, "error": "Không tìm thấy dữ liệu gòn."}, status_code=404)
        db.commit()
    except Exception as e:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    return JSONResponse(
        {
            "ok": True,
            "item_id": item.id,
            "ngay_nhap": item.ngay_nhap.isoformat() if item.ngay_nhap else "",
        }
    )


@router.get("/wms/receipts/{receipt_id}", response_class=HTMLResponse)
def receipt_detail(request: Request, receipt_id: int, db: Session = Depends(get_db)):
    receipt = get_receipt(db, receipt_id=receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y phiáº¿u.")
    lines = get_receipt_lines(db, receipt_id=receipt_id)
    return templates.TemplateResponse(
        request,
        "wms/receipt_detail.html",
        {
            "title": f"Phiếu #{receipt.id}",
            "receipt": receipt,
            "lines": lines,
            "warnings": [],
        },
    )


@router.get("/wms/receipts/{receipt_id}/pdf")
def receipt_pdf(receipt_id: int, db: Session = Depends(get_db)):
    receipt = get_receipt(db, receipt_id=receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y phiáº¿u.")
    lines = get_receipt_lines(db, receipt_id=receipt_id)
    pdf_bytes = render_receipt_pdf(receipt, lines)
    filename = f"receipt_{receipt.id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/wms/hanging", response_class=HTMLResponse)
def hanging_list(request: Request, db: Session = Depends(get_db)):
    error: str | None = None
    selected_nhu_caus = _selected_nhu_caus(request)
    try:
        # Backfill once if table exists but still empty (imports happened before hanging_tags existed).
        existing_any = db.query(HangingTag.id).limit(1).all()
        if not existing_any:
            created = backfill_hanging_tags(db, receipt_limit=200)
            if created:
                db.commit()

        nhu_cau_options = [
            r[0]
            for r in db.query(HangingTag.nhu_cau)
            .filter(HangingTag.nhu_cau.isnot(None))
            .distinct()
            .order_by(HangingTag.nhu_cau.asc())
            .all()
            if r[0]
        ]

        q = db.query(HangingTag)
        if selected_nhu_caus:
            q = q.filter(HangingTag.nhu_cau.in_(selected_nhu_caus))
        tags = q.order_by(HangingTag.id.desc()).limit(500).all()

        # Fill missing fields (customer/ngay_xuat) for old tags without overwriting existing values.
        changed = fill_missing_hanging_fields(db, tag_ids=[t.id for t in tags])
        if changed:
            db.commit()
            tags = q.order_by(HangingTag.id.desc()).limit(500).all()
    except ProgrammingError as e:
        # Typically happens before running Alembic migrations.
        error = str(e.orig) if getattr(e, "orig", None) else str(e)
        tags = []
        nhu_cau_options = []
    return templates.TemplateResponse(
        request,
        "wms/hanging_list.html",
        {
            "title": "Bảng treo",
            "tab": "regular",
            "tags": tags,
            "gon_items": [],
            "error": error,
            "nhu_cau": selected_nhu_caus[0] if len(selected_nhu_caus) == 1 else None,
            "selected_nhu_caus": selected_nhu_caus,
            "current_nhu_cau_query": _nhu_cau_query_string(selected_nhu_caus),
            "nhu_cau_options": nhu_cau_options,
        },
    )


@router.get("/wms/hanging/gon", response_class=HTMLResponse)
def hanging_gon_list(request: Request, db: Session = Depends(get_db)):
    gon_error: str | None = None
    try:
        gon_items = list_gon_receipts(db, limit=500)
    except ProgrammingError as e:
        gon_items = []
        gon_error = str(e.orig) if getattr(e, "orig", None) else str(e)
    return templates.TemplateResponse(
        request,
        "wms/hanging_list.html",
        {
            "title": "Bảng treo",
            "tab": "gon",
            "tags": [],
            "gon_items": gon_items,
            "error": gon_error,
            "nhu_cau": None,
            "selected_nhu_caus": [],
            "current_nhu_cau_query": "",
            "nhu_cau_options": [],
        },
    )


@router.get("/wms/hanging/gon/print", response_class=HTMLResponse)
def hanging_gon_print(
    request: Request,
    db: Session = Depends(get_db),
    ids: list[int] | None = Query(default=None),
):
    try:
        items = (
            list_gon_receipts_by_ids(db, ids=ids)
            if ids
            else list_gon_receipts(db, limit=500)
        )
    except ProgrammingError:
        items = []
    return templates.TemplateResponse(
        request,
        "wms/hanging_gon_print.html",
        {"title": "In bảng treo gòn", "items": items},
    )


@router.get("/wms/hanging/{tag_id}/pdf")
def hanging_pdf(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")
    pdf_bytes = render_hanging_tag_pdf(tag)
    filename = f"bang_treo_{tag.id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )


@router.get("/wms/hanging/merge-print", response_class=HTMLResponse)
def hanging_merge_print(
    request: Request,
    db: Session = Depends(get_db),
    ids: list[int] | None = Query(default=None),
):
    if not ids:
        raise HTTPException(status_code=400, detail="Chưa chọn bảng treo nào.")
    tags = db.query(HangingTag).filter(HangingTag.id.in_(ids)).order_by(HangingTag.id.asc()).all()
    if not tags:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")

    import types

    def _uniq_join(vals, sep: str = " / ") -> str:
        seen: list[str] = []
        for v in vals:
            s = (v or "").strip()
            if s and s not in seen:
                seen.append(s)
        return sep.join(seen)

    def _uniq_list(vals) -> list[str]:
        seen: list[str] = []
        for v in vals:
            s = (v or "").strip()
            if s and s not in seen:
                seen.append(s)
        return seen

    lot_lines = _uniq_list(t.lot for t in tags)
    merged = types.SimpleNamespace(
        khach_hang=(tags[0].khach_hang or "DECATHLON").strip() or "DECATHLON",
        nha_cung_cap=_uniq_join(t.nha_cung_cap for t in tags),
        customer=_uniq_join(t.customer for t in tags),
        ngay_nhap_hang=min((t.ngay_nhap_hang for t in tags if t.ngay_nhap_hang), default=None),
        ma_hang=_uniq_join(t.ma_hang for t in tags),
        nhu_cau=_uniq_join(t.nhu_cau for t in tags),
        loai_vai=_uniq_join(t.loai_vai for t in tags),
        ma_art=_uniq_join(t.ma_art for t in tags),
        mau_vai=_uniq_join(t.mau_vai for t in tags),
        ma_mau=_uniq_join(t.ma_mau for t in tags),
        lot=lot_lines[0] if len(lot_lines) == 1 else "",
        lot_lines=lot_lines,
        ket_qua_kiem_tra=tags[0].ket_qua_kiem_tra if tags else "OK",
    )
    return templates.TemplateResponse(
        request,
        "wms/hanging_print.html",
        {"title": "Gộp bảng treo", "tags": [merged]},
    )


@router.get("/wms/hanging/print", response_class=HTMLResponse)
def hanging_print(
    request: Request,
    db: Session = Depends(get_db),
    ids: list[int] | None = Query(default=None),
    nhu_cau: list[str] | None = Query(default=None),
):
    selected_nhu_caus = [v.strip() for v in (nhu_cau or []) if (v or "").strip()]
    if ids:
        tags = db.query(HangingTag).filter(HangingTag.id.in_(ids)).order_by(HangingTag.id.asc()).all()
    elif selected_nhu_caus:
        tags = (
            db.query(HangingTag)
            .filter(HangingTag.nhu_cau.in_(selected_nhu_caus))
            .order_by(HangingTag.lot.asc(), HangingTag.id.asc())
            .all()
        )
    else:
        tags = db.query(HangingTag).order_by(HangingTag.lot.asc(), HangingTag.id.asc()).all()

    return templates.TemplateResponse(
        request,
        "wms/hanging_print.html",
        {"title": "In bảng treo", "tags": tags},
    )


@router.get("/wms/hanging/{tag_id}/edit", response_class=HTMLResponse)
def hanging_edit(request: Request, tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")
    current_nhu_cau_query = _nhu_cau_query_string(_selected_nhu_caus(request))
    return templates.TemplateResponse(
        request,
        "wms/hanging_edit.html",
        {"title": f"Sửa bảng treo #{tag.id}", "tag": tag, "current_nhu_cau_query": current_nhu_cau_query},
    )


@router.get("/wms/hanging/{tag_id}/edit/fragment", response_class=HTMLResponse)
def hanging_edit_fragment(request: Request, tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")
    current_nhu_cau_query = _nhu_cau_query_string(_selected_nhu_caus(request))
    return templates.TemplateResponse(
        request,
        "wms/_hanging_edit_fragment.html",
        {"tag": tag, "current_nhu_cau_query": current_nhu_cau_query},
    )


@router.post("/wms/hanging/{tag_id}/edit/fragment")
def hanging_edit_fragment_save(
    request: Request,
    tag_id: int,
    db: Session = Depends(get_db),
    customer: str | None = Form(default=None),
    ngay_xuat: date | None = Form(default=None),
):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        return JSONResponse({"ok": False, "error": "Không tìm thấy bảng treo."}, status_code=404)

    try:
        tag.customer = (customer or "").strip() or None
        tag.ngay_xuat = ngay_xuat

        # Also keep supplier in sync for printing convenience when customer is provided.
        if tag.customer:
            tag.nha_cung_cap = tag.customer

        db.add(tag)
        db.commit()
    except Exception as e:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    return JSONResponse(
        {
            "ok": True,
            "tag_id": tag.id,
            "customer": tag.customer,
            "ngay_xuat": tag.ngay_xuat.isoformat() if tag.ngay_xuat else "",
        }
    )


@router.post("/wms/hanging/{tag_id}/edit")
def hanging_edit_save(
    request: Request,
    tag_id: int,
    db: Session = Depends(get_db),
    customer: str | None = Form(default=None),
    ngay_xuat: date | None = Form(default=None),
):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")

    tag.customer = (customer or "").strip() or None
    tag.ngay_xuat = ngay_xuat

    # Also keep supplier in sync for printing convenience when customer is provided.
    if tag.customer:
        tag.nha_cung_cap = tag.customer

    db.add(tag)
    db.commit()

    current_nhu_cau_query = _nhu_cau_query_string(_selected_nhu_caus(request))
    url = "/wms/hanging"
    if current_nhu_cau_query:
        url = f"/wms/hanging?{current_nhu_cau_query}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/wms/stock", response_class=HTMLResponse)
def stock_check_home(request: Request, db: Session = Depends(get_db)):
    stock_tab = (request.query_params.get("tab") or "fabric").strip() or "fabric"
    if stock_tab not in {"fabric", "gon"}:
        stock_tab = "fabric"
    nhu_cau = request.query_params.get("nhu_cau")
    lot = request.query_params.get("lot")

    nhu_cau_options = list_nhu_cau_options(db)
    # Keep selected demand visible even if it has just become completed.
    if nhu_cau and nhu_cau not in nhu_cau_options:
        nhu_cau_options = [nhu_cau, *nhu_cau_options]

    lot_options = list_lot_options(db, nhu_cau=nhu_cau) if nhu_cau else []
    # If user is viewing a completed lot via query params (e.g., after save redirect),
    # keep it in the dropdown so the selection stays visible.
    if lot and lot not in lot_options:
        lot_options = [lot, *lot_options]

    lot_summaries = list_incomplete_lot_summaries(db, nhu_cau=nhu_cau) if nhu_cau else []
    rows = get_roll_rows(db, nhu_cau=nhu_cau, lot=lot) if (nhu_cau and lot) else []
    gon_type_options = list_gon_type_options(db)
    gon_rows = list_recent_gon_stock_entries(db, limit=30)
    return templates.TemplateResponse(
        request,
        "wms/stock_check.html",
        {
            "title": "Nhập kho / kiểm kho",
            "stock_tab": stock_tab,
            "nhu_cau": nhu_cau,
            "lot": lot,
            "nhu_cau_options": nhu_cau_options,
            "lot_options": lot_options,
            "lot_summaries": lot_summaries,
            "rows": rows,
            "gon_type_options": gon_type_options,
            "gon_rows": gon_rows,
            "warehouse_area_options": warehouse_area_options(),
            "expanded_block_options": expanded_block_options(),
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
            "line_pallet_map": pallet_options_by_line(),
        },
    )


@router.post("/wms/stock")
async def stock_check_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    nhu_cau = (form.get("nhu_cau") or "").strip()
    lot = (form.get("lot") or "").strip()
    if not nhu_cau or not lot:
        raise HTTPException(status_code=400, detail="Thiáº¿u Nhu cáº§u hoáº·c Lot.")

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0

    items: list[dict] = []
    for i in range(row_count):
        ma_cay = (form.get(f"ma_cay_{i}") or "").strip()
        if not ma_cay:
            continue

        def to_float(v: object) -> float | None:
            if v is None:
                return None
            s = str(v).strip().replace(",", "")
            if not s:
                return None
            try:
                return float(s)
            except Exception:
                return None

        expected = to_float(form.get(f"expected_{i}"))
        full_checked = form.get(f"full_{i}") in ("on", "true", "1", "yes")
        actual = expected if full_checked else to_float(form.get(f"actual_{i}"))
        note = (form.get(f"note_{i}") or "").strip() or None

        # Only persist if user confirmed full OR provided actual OR note.
        if not full_checked and actual is None and not note:
            continue

        items.append(
            {
                "ma_cay": ma_cay,
                "expected_yards": expected,
                "actual_yards": actual,
                "note": note,
            }
        )

    upsert_stock_checks(db, nhu_cau=nhu_cau, lot=lot, items=items)
    db.commit()

    return RedirectResponse(url=f"/wms/stock?tab=fabric&nhu_cau={nhu_cau}&lot={lot}&saved=1", status_code=303)


@router.post("/wms/stock/gon")
async def gon_stock_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    gon_type = (form.get("gon_type") or "").strip()
    warehouse_area = (form.get("warehouse_area") or "").strip() or "expanded"
    tang = (form.get("tang") or "").strip() or None
    line = (form.get("line") or "").strip() or None
    pallet = (form.get("pallet") or "").strip() or None
    block = (form.get("block") or "").strip() or None

    def to_int(v: object) -> int | None:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return int(float(s))
        except Exception:
            return None

    def to_float(v: object) -> float | None:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    so_kien = to_int(form.get("so_kien"))
    so_yds = to_float(form.get("so_yds"))
    vi_tri = build_location_code(
        warehouse_area=warehouse_area,
        tang=tang,
        line=line,
        pallet=pallet,
        block=block,
    )

    if not gon_type or so_kien is None or so_kien <= 0 or so_yds is None or so_yds <= 0 or not vi_tri:
        raise HTTPException(status_code=400, detail="Thiếu hoặc sai dữ liệu nhập gòn.")

    create_gon_stock_entry(
        db,
        gon_type=gon_type,
        so_kien=so_kien,
        so_yds=so_yds,
        warehouse_area=warehouse_area,
        tang=tang,
        line=line,
        pallet=pallet,
        block=block,
        vi_tri=vi_tri,
    )
    db.commit()

    return RedirectResponse(url="/wms/stock?tab=gon&saved=1", status_code=303)


@router.get("/wms/stock/locations", response_class=HTMLResponse)
def location_home(request: Request, db: Session = Depends(get_db)):
    nhu_cau = request.query_params.get("nhu_cau")
    anh_mau = request.query_params.get("anh_mau")
    lot = request.query_params.get("lot")

    nhu_cau_options = list_nhu_cau_options_for_location(db)
    if nhu_cau and nhu_cau not in nhu_cau_options:
        nhu_cau_options = [nhu_cau, *nhu_cau_options]
    anh_mau_options = list_anh_mau_options(db, nhu_cau=nhu_cau) if nhu_cau else []
    lot_options = list_lot_options_for_location(db, nhu_cau=nhu_cau, anh_mau=anh_mau) if nhu_cau else []
    if lot and lot not in lot_options:
        lot_options = [lot, *lot_options]

    rows = list_rolls_for_location(db, nhu_cau=nhu_cau, anh_mau=anh_mau, lot=lot) if (nhu_cau and lot) else []
    return templates.TemplateResponse(
        request,
        "wms/location_assign.html",
        {
            "title": "Định danh vị trí",
            "nhu_cau": nhu_cau,
            "anh_mau": anh_mau,
            "lot": lot,
            "nhu_cau_options": nhu_cau_options,
            "anh_mau_options": anh_mau_options,
            "lot_options": lot_options,
            "rows": rows,
            "warehouse_area_options": warehouse_area_options(),
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
            "line_pallet_map": pallet_options_by_line(),
            "expanded_block_options": expanded_block_options(),
        },
    )


@router.post("/wms/stock/locations")
async def location_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    nhu_cau = (form.get("nhu_cau") or "").strip()
    anh_mau = (form.get("anh_mau") or "").strip() or None
    lot = (form.get("lot") or "").strip()
    warehouse_area = (form.get("warehouse_area") or "").strip() or "main"
    tang = (form.get("tang") or "").strip() or None
    line = (form.get("line") or "").strip() or None
    pallet = (form.get("pallet") or "").strip() or None
    block = (form.get("block") or "").strip() or None
    vi_tri = build_location_code(
        warehouse_area=warehouse_area,
        tang=tang,
        line=line,
        pallet=pallet,
        block=block,
    )
    if not nhu_cau or not lot or not vi_tri:
        raise HTTPException(status_code=400, detail="Thiáº¿u thÃ´ng tin lá»c hoáº·c vá»‹ trÃ­.")

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0

    ma_cays: list[str] = []
    for i in range(row_count):
        if form.get(f"sel_{i}") in ("on", "true", "1", "yes"):
            ma = (form.get(f"ma_cay_{i}") or "").strip()
            if ma:
                ma_cays.append(ma)

    if not ma_cays:
        raise HTTPException(status_code=400, detail="ChÆ°a chá»n cÃ¢y váº£i nÃ o.")

    assign_location(db, nhu_cau=nhu_cau, lot=lot, anh_mau=anh_mau, ma_cays=ma_cays, vi_tri=vi_tri)
    db.commit()
    return RedirectResponse(
        url=f"/wms/stock/locations?nhu_cau={nhu_cau}&anh_mau={anh_mau or ''}&lot={lot}&saved=1",
        status_code=303,
    )


@router.get("/wms/issue", response_class=HTMLResponse)
def issue_home(request: Request, db: Session = Depends(get_db)):
    material = (request.query_params.get("material") or "fabric").strip() or "fabric"
    if material not in {"fabric", "gon"}:
        material = "fabric"
    nhu_cau = request.query_params.get("nhu_cau")
    lot = request.query_params.get("lot")
    tab = request.query_params.get("tab") or "issue"
    gon_type = (request.query_params.get("gon_type") or "").strip()
    gon_vi_tri = (request.query_params.get("gon_vi_tri") or "").strip()

    nhu_cau_options = list_issue_nhu_cau_options(db) if material == "fabric" else []
    lot_options = list_issue_lot_options(db, nhu_cau=nhu_cau) if (material == "fabric" and nhu_cau) else []
    if material == "fabric" and lot and lot not in lot_options:
        lot_options = [lot, *lot_options]

    candidates = list_issue_candidates(db, nhu_cau=nhu_cau, lot=lot) if (material == "fabric" and tab == "issue" and nhu_cau and lot) else []
    gon_type_options = list_gon_issue_type_options(db) if material == "gon" else []
    gon_vi_tri_options = list_gon_issue_location_options(db, gon_type=gon_type) if (material == "gon" and gon_type) else []
    gon_candidates = list_gon_issue_candidates(db, gon_type=gon_type or None, vi_tri=gon_vi_tri or None) if (material == "gon" and tab == "issue") else []

    # history
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    def parse_date(s: str | None):
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except Exception:
            return None

    df = parse_date(date_from)
    dt = parse_date(date_to)
    issues = list_issue_history(db, date_from=df, date_to=dt, nhu_cau=nhu_cau) if (material == "fabric" and tab == "history") else []
    counts = count_issue_lines(db, issue_ids=[i.id for i in issues]) if issues else {}
    gon_issues = list_gon_issue_history(db, gon_type=gon_type or None, date_from=df, date_to=dt) if (material == "gon" and tab == "history") else []

    return templates.TemplateResponse(
        request,
        "wms/issue.html",
        {
            "title": "Xuất kho",
            "material": material,
            "tab": tab,
            "nhu_cau": nhu_cau,
            "lot": lot,
            "gon_type": gon_type,
            "gon_vi_tri": gon_vi_tri,
            "date_from": date_from,
            "date_to": date_to,
            "nhu_cau_options": nhu_cau_options,
            "lot_options": lot_options,
            "candidates": candidates,
            "gon_type_options": gon_type_options,
            "gon_vi_tri_options": gon_vi_tri_options,
            "gon_candidates": gon_candidates,
            "issues": issues,
            "gon_issues": gon_issues,
            "issue_counts": counts,
        },
    )


@router.post("/wms/issue")
async def issue_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    nhu_cau = (form.get("nhu_cau") or "").strip()
    lot = (form.get("lot") or "").strip()
    ngay_xuat_s = (form.get("ngay_xuat") or "").strip()
    status = (form.get("status") or "").strip() or "Cáº¥p phÃ¡t sáº£n xuáº¥t"
    note = (form.get("note") or "").strip() or None
    if not nhu_cau or not lot or not ngay_xuat_s:
        raise HTTPException(status_code=400, detail="Thiáº¿u Nhu cáº§u/Lot/NgÃ y xuáº¥t.")
    try:
        ngay_xuat = date.fromisoformat(ngay_xuat_s)
    except Exception as e:
        raise HTTPException(status_code=400, detail="NgÃ y xuáº¥t khÃ´ng há»£p lá»‡.") from e

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0
    ma_cays: list[str] = []
    for i in range(row_count):
        if form.get(f"sel_{i}") in ("on", "true", "1", "yes"):
            ma = (form.get(f"ma_cay_{i}") or "").strip()
            if ma:
                ma_cays.append(ma)
    if not ma_cays:
        raise HTTPException(status_code=400, detail="ChÆ°a chá»n MÃ£ cÃ¢y.")

    issue_id = create_issue(db, nhu_cau=nhu_cau, lot=lot, ngay_xuat=ngay_xuat, status=status, note=note, ma_cays=ma_cays)
    db.commit()
    return RedirectResponse(url=f"/wms/issue?material=fabric&nhu_cau={nhu_cau}&lot={lot}&saved=1#issue", status_code=303)


@router.post("/wms/issue/gon")
async def gon_issue_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    gon_type = (form.get("gon_type") or "").strip()
    gon_vi_tri = (form.get("gon_vi_tri") or "").strip()
    ngay_xuat_s = (form.get("ngay_xuat") or "").strip()
    note = (form.get("note") or "").strip() or None

    def to_float(v: object) -> float | None:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    so_kien = to_float(form.get("so_kien"))
    so_yds = to_float(form.get("so_yds"))
    if not gon_type or not gon_vi_tri or so_kien is None or so_kien <= 0 or so_yds is None or so_yds <= 0 or not ngay_xuat_s:
        raise HTTPException(status_code=400, detail="Thiếu dữ liệu xuất gòn.")
    try:
        ngay_xuat = date.fromisoformat(ngay_xuat_s)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Ngày xuất không hợp lệ.") from e

    try:
        create_gon_issue(
            db,
            gon_type=gon_type,
            from_vi_tri=gon_vi_tri,
            so_kien=so_kien,
            so_yds=so_yds,
            ngay_xuat=ngay_xuat,
            note=note,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    return RedirectResponse(url=f"/wms/issue?material=gon&gon_type={gon_type}&gon_vi_tri={gon_vi_tri}&saved=1", status_code=303)


@router.get("/wms/stock/returns", response_class=HTMLResponse)
def returns_home(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get("tab") or "todo"
    nhu_cau = (request.query_params.get("nhu_cau") or "").strip()
    lot = (request.query_params.get("lot") or "").strip()
    loai_vai = (request.query_params.get("loai_vai") or "").strip()

    # history filter
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    def parse_date(s: str | None):
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except Exception:
            return None

    df = parse_date(date_from)
    dt = parse_date(date_to)

    candidate_limit = 5000 if (nhu_cau or lot or loai_vai) else 300
    candidates = (
        list_return_candidates(
            db,
            nhu_cau=nhu_cau or None,
            lot=lot or None,
            ten_art=loai_vai or None,
            limit=candidate_limit,
        )
        if tab == "todo"
        else []
    )
    history = list_return_history(db, date_from=df, date_to=dt) if tab == "history" else []

    return templates.TemplateResponse(
        request,
        "wms/returns.html",
        {
            "title": "Tái nhập kho",
            "tab": tab,
            "candidates": candidates,
            "history": history,
            "filter_nhu_cau": nhu_cau,
            "filter_lot": lot,
            "filter_loai_vai": loai_vai,
            "nhu_cau_options": list_pending_return_nhu_cau_options(db, limit=2000) if tab == "todo" else [],
            "lot_options": list_pending_return_lot_options(db, limit=2000) if tab == "todo" else [],
            "loai_vai_options": list_pending_return_ten_art_options(db, limit=2000) if tab == "todo" else [],
            "warehouse_area_options": warehouse_area_options(),
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
            "line_pallet_map": pallet_options_by_line(),
            "expanded_block_options": expanded_block_options(),
        },
    )


@router.post("/wms/stock/returns")
async def returns_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    issue_line_id = int(form.get("issue_line_id") or 0)
    ma_cay = (form.get("ma_cay") or "").strip()
    ngay_s = (form.get("ngay_tai_nhap") or "").strip()
    status = (form.get("status") or "").strip() or "Tái nhập kho"
    note = (form.get("note") or "").strip() or None
    nhu_cau_moi = (form.get("nhu_cau_moi") or "").strip() or None
    lot_moi = (form.get("lot_moi") or "").strip() or None

    def to_float(v: object) -> float | None:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    yds_du = to_float(form.get("yds_du"))

    if not issue_line_id or not ma_cay or not ngay_s:
        raise HTTPException(status_code=400, detail="Thiếu dữ liệu.")
    try:
        ngay_tai_nhap = date.fromisoformat(ngay_s)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Ngày tái nhập không hợp lệ.") from e

    vi_tri_moi = None
    if status in {"Tái nhập kho", "TÃ¡i nháº­p kho"}:
        warehouse_area = (form.get("warehouse_area") or "").strip() or "main"
        tang = (form.get("tang") or "").strip() or None
        line = (form.get("line") or "").strip() or None
        pallet = (form.get("pallet") or "").strip() or None
        block = (form.get("block") or "").strip() or None
        vi_tri_moi = build_location_code(
            warehouse_area=warehouse_area,
            tang=tang,
            line=line,
            pallet=pallet,
            block=block,
        )
        if not vi_tri_moi:
            raise HTTPException(status_code=400, detail="Thiếu vị trí mới.")

    create_return(
        db,
        issue_line_id=issue_line_id,
        ma_cay=ma_cay,
        ngay_tai_nhap=ngay_tai_nhap,
        yds_du=yds_du,
        status=status,
        nhu_cau_moi=nhu_cau_moi,
        lot_moi=lot_moi,
        vi_tri_moi=vi_tri_moi,
        note=note,
    )
    db.commit()
    return RedirectResponse(url="/wms/stock/returns?saved=1", status_code=303)


@router.get("/wms/tools", response_class=HTMLResponse)
def tools_home(request: Request):
    return templates.TemplateResponse(
        request,
        "wms/tools_home.html",
        {"title": "Tính năng khác"},
    )


@router.get("/wms/tools/pallet-stock-check", response_class=HTMLResponse)
def tools_pallet_stock_check(request: Request, db: Session = Depends(get_db)):
    tab = (request.query_params.get("tab") or "audit").strip() or "audit"
    if tab not in {"audit", "report"}:
        tab = "audit"
    tang = (request.query_params.get("tang") or "A").strip() or "A"
    line = (request.query_params.get("line") or "01").strip() or "01"
    pallet = (request.query_params.get("pallet") or "01").strip() or "01"
    vi_tri = build_location_code(warehouse_area="main", tang=tang, line=line, pallet=pallet) or "A.01.01"
    parsed = parse_location_code(vi_tri)
    rows = get_pallet_audit_rows(db, vi_tri=vi_tri)
    lot_summary_map: dict[str, int] = {}
    for row in rows:
        lot_key = (row.lot or "").strip() or "Không có Lot"
        lot_summary_map[lot_key] = lot_summary_map.get(lot_key, 0) + 1
    lot_summaries = [
        {"lot": lot, "count": count}
        for lot, count in sorted(lot_summary_map.items(), key=lambda item: item[0])
    ]
    sessions = list_pallet_audit_sessions(db, limit=120)
    return templates.TemplateResponse(
        request,
        "wms/tools_pallet_stock_check.html",
        {
            "title": "Kiểm tồn kho theo pallet",
            "tab": tab,
            "vi_tri": vi_tri,
            "tang": parsed["tang"] or tang,
            "line": parsed["line"] or line,
            "pallet": parsed["pallet"] or pallet,
            "rows": rows,
            "total_roll_count": len(rows),
            "lot_summaries": lot_summaries,
            "sessions": sessions,
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
            "line_pallet_map": pallet_options_by_line(),
        },
    )


@router.get("/wms/tools/pallet-stock-check/search")
def tools_pallet_stock_check_search(
    q: str = Query(default=""),
    vi_tri: str = Query(default=""),
    lot: str = Query(default=""),
    db: Session = Depends(get_db),
):
    rows = search_pallet_audit_rolls(db, q=q, vi_tri=vi_tri, lot=lot, limit=12)
    return JSONResponse(
        {
            "items": [
                {
                    "ma_cay": row.ma_cay,
                    "nhu_cau": row.nhu_cau,
                    "lot": row.lot,
                    "system_yards": row.system_yards,
                    "vi_tri": row.vi_tri,
                }
                for row in rows
            ]
        }
    )


@router.get("/wms/tools/pallet-stock-check/search-lots")
def tools_pallet_stock_check_search_lots(
    q: str = Query(default=""),
    vi_tri: str = Query(default=""),
    db: Session = Depends(get_db),
):
    rows = search_pallet_audit_lots(db, q=q, vi_tri=vi_tri, limit=12)
    return JSONResponse(
        {
            "items": [
                {
                    "lot": row.lot,
                    "roll_count": row.roll_count,
                }
                for row in rows
            ]
        }
    )


@router.get("/wms/tools/pallet-stock-check/sessions/{session_id}")
def tools_pallet_stock_check_session_detail(session_id: int, db: Session = Depends(get_db)):
    detail = get_pallet_audit_session_detail(db, session_id=session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt kiểm.")
    return JSONResponse(
        {
            "session_id": detail.session_id,
            "created_at": detail.created_at.isoformat() if detail.created_at else None,
            "vi_tri": detail.vi_tri,
            "app_roll_count": detail.app_roll_count,
            "matched_roll_count": detail.matched_roll_count,
            "extra_roll_count": detail.extra_roll_count,
            "rows": [
                {
                    "ma_cay": row.ma_cay,
                    "nhu_cau": row.nhu_cau,
                    "lot": row.lot,
                    "system_yards": row.system_yards,
                    "present_actual": row.present_actual,
                    "expected_in_system": row.expected_in_system,
                    "vi_tri_he_thong": row.vi_tri_he_thong,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in detail.rows
            ],
        }
    )


@router.post("/wms/tools/pallet-stock-check")
async def tools_pallet_stock_check_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    tang = (form.get("tang") or "A").strip() or "A"
    line = (form.get("line") or "01").strip() or "01"
    pallet = (form.get("pallet") or "01").strip() or "01"
    vi_tri = build_location_code(warehouse_area="main", tang=tang, line=line, pallet=pallet)
    if not vi_tri:
        raise HTTPException(status_code=400, detail="Pallet không hợp lệ.")

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0
    try:
        extra_count = int(form.get("extra_count") or 0)
    except Exception:
        extra_count = 0

    present_ma_cays: list[str] = []
    for i in range(row_count):
        if form.get(f"present_{i}") not in ("on", "true", "1", "yes"):
            continue
        ma_cay = (form.get(f"ma_cay_{i}") or "").strip()
        if ma_cay:
            present_ma_cays.append(ma_cay)

    extra_ma_cays: list[str] = []
    for i in range(extra_count):
        ma_cay = (form.get(f"extra_ma_cay_{i}") or "").strip()
        if ma_cay:
            extra_ma_cays.append(ma_cay)

    save_pallet_audit(
        db,
        vi_tri=vi_tri,
        present_ma_cays=present_ma_cays,
        extra_ma_cays=extra_ma_cays,
    )
    db.commit()
    return RedirectResponse(url=f"/wms/tools/pallet-stock-check?tang={tang}&line={line}&pallet={pallet}&saved=1", status_code=303)


@router.get("/wms/tools/trace", response_class=HTMLResponse)
def tools_trace(request: Request, db: Session = Depends(get_db)):
    lot = request.query_params.get("lot") or ""
    ma_cay = request.query_params.get("ma_cay") or ""
    lot_options = list_trace_lots(db, ma_cay=ma_cay, limit=2000)
    ma_cay_options = list_trace_ma_cays(db, lot=lot, limit=5000)
    events = build_trace_timeline(db, lot=lot, ma_cay=ma_cay) if ma_cay else []
    return templates.TemplateResponse(
        request,
        "wms/tools_trace.html",
        {
            "title": "Truy xuất cây vải",
            "lot": lot,
            "ma_cay": ma_cay,
            "lot_options": lot_options,
            "ma_cay_options": ma_cay_options,
            "events": events,
        },
    )


@router.get("/wms/tools/demand-transfer", response_class=HTMLResponse)
def tools_demand_transfer(request: Request, db: Session = Depends(get_db)):
    from_nhu_cau = request.query_params.get("from_nhu_cau") or "NC-TAM"
    # list candidates by current demand
    from fabric_warehouse.db.models.location_assignment import LocationAssignment

    nhu_cau_options = [
        r[0]
        for r in db.query(LocationAssignment.nhu_cau)
        .filter(LocationAssignment.nhu_cau.isnot(None))
        .distinct()
        .order_by(LocationAssignment.nhu_cau.asc())
        .all()
        if r[0]
    ]

    rows = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.nhu_cau == from_nhu_cau)
        .order_by(LocationAssignment.lot.asc(), LocationAssignment.vi_tri.asc(), LocationAssignment.ma_cay.asc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "wms/tools_demand_transfer.html",
        {
            "title": "Điều chuyển nhu cầu",
            "from_nhu_cau": from_nhu_cau,
            "rows": rows,
            "nhu_cau_options": nhu_cau_options,
        },
    )


@router.post("/wms/tools/demand-transfer")
async def tools_demand_transfer_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    to_nhu_cau = (form.get("to_nhu_cau") or "").strip()
    to_lot = (form.get("to_lot") or "").strip() or None
    note = (form.get("note") or "").strip() or None
    from_nhu_cau = (form.get("from_nhu_cau") or "").strip() or "NC-TAM"

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0
    ma_cays: list[str] = []
    for i in range(row_count):
        if form.get(f"sel_{i}") in ("on", "true", "1", "yes"):
            ma = (form.get(f"ma_cay_{i}") or "").strip()
            if ma:
                ma_cays.append(ma)
    if not ma_cays:
        raise HTTPException(status_code=400, detail="ChÆ°a chá»n cÃ¢y.")

    transfer_demand(db, ma_cays=ma_cays, to_nhu_cau=to_nhu_cau, to_lot=to_lot, note=note)
    db.commit()
    return RedirectResponse(url=f"/wms/tools/demand-transfer?from_nhu_cau={from_nhu_cau}&saved=1", status_code=303)


@router.get("/wms/tools/location-transfer", response_class=HTMLResponse)
def tools_location_transfer(request: Request, db: Session = Depends(get_db)):
    material = (request.query_params.get("material") or "fabric").strip() or "fabric"
    if material not in {"fabric", "gon"}:
        material = "fabric"
    warehouse_area = (request.query_params.get("warehouse_area") or "main").strip() or "main"
    tang = request.query_params.get("tang") or "A"
    line = request.query_params.get("line") or "01"
    pallet = request.query_params.get("pallet") or "01"
    block = request.query_params.get("block") or "A1"
    vi_tri = build_location_code(
        warehouse_area=warehouse_area,
        tang=tang,
        line=line,
        pallet=pallet,
        block=block,
    ) or "A.01.01"
    parsed = parse_location_code(vi_tri)

    from fabric_warehouse.db.models.location_assignment import LocationAssignment

    rows = []
    gon_type = (request.query_params.get("gon_type") or "").strip()
    gon_rows = []
    gon_type_options = []
    if material == "fabric":
        rows = (
            db.query(LocationAssignment)
            .filter(LocationAssignment.vi_tri == vi_tri)
            .filter(LocationAssignment.trang_thai.in_(("Đang lưu", "Dang luu", "Đang luu", "Dang lưu")))
            .order_by(LocationAssignment.ma_cay.asc())
            .all()
        )
    else:
        gon_rows = list_gon_issue_candidates(db, gon_type=gon_type or None, vi_tri=vi_tri)
        gon_type_options = sorted({row.gon_type for row in list_gon_issue_candidates(db, vi_tri=vi_tri)})
    return templates.TemplateResponse(
        request,
        "wms/tools_location_transfer.html",
        {
            "title": "Điều chuyển vị trí",
            "material": material,
            "warehouse_area": parsed["warehouse_area"],
            "tang": parsed["tang"] or tang,
            "line": parsed["line"] or line,
            "pallet": parsed["pallet"] or pallet,
            "block": parsed["block"] or block,
            "vi_tri": vi_tri,
            "rows": rows,
            "gon_type": gon_type,
            "gon_rows": gon_rows,
            "gon_type_options": gon_type_options,
            "gon_transfer_history": list_gon_transfer_history(db, limit=100) if material == "gon" else [],
            "warehouse_area_options": warehouse_area_options(),
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
            "line_pallet_map": pallet_options_by_line(),
            "expanded_block_options": expanded_block_options(),
        },
    )


@router.post("/wms/tools/location-transfer")
async def tools_location_transfer_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    material = (form.get("material") or "fabric").strip() or "fabric"
    if material == "gon":
        gon_type = (form.get("gon_type") or "").strip()
        from_vi_tri = (form.get("from_vi_tri") or "").strip()
        to_block = (form.get("to_block") or "").strip()
        note = (form.get("note") or "").strip() or None

        def to_float(v: object) -> float | None:
            if v is None:
                return None
            s = str(v).strip().replace(",", "")
            if not s:
                return None
            try:
                return float(s)
            except Exception:
                return None

        so_kien = to_float(form.get("so_kien"))
        so_yds = to_float(form.get("so_yds"))
        to_vi_tri = build_location_code(warehouse_area="expanded", block=to_block)
        if not gon_type or not from_vi_tri or not to_vi_tri or so_kien is None or so_kien <= 0 or so_yds is None or so_yds <= 0:
            raise HTTPException(status_code=400, detail="Thiếu dữ liệu điều chuyển gòn.")
        try:
            create_gon_transfer(
                db,
                gon_type=gon_type,
                from_vi_tri=from_vi_tri,
                to_vi_tri=to_vi_tri,
                so_kien=so_kien,
                so_yds=so_yds,
                note=note,
            )
            db.commit()
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e)) from e
        return RedirectResponse(url=f"/wms/tools/location-transfer?material=gon&warehouse_area=expanded&block={to_block}&saved=1", status_code=303)

    to_warehouse_area = (form.get("to_warehouse_area") or "").strip() or "main"
    to_tang = (form.get("to_tang") or "").strip() or None
    to_line = (form.get("to_line") or "").strip() or None
    to_pallet = (form.get("to_pallet") or "").strip() or None
    to_block = (form.get("to_block") or "").strip() or None
    note = (form.get("note") or "").strip() or None
    to_vi_tri = build_location_code(
        warehouse_area=to_warehouse_area,
        tang=to_tang,
        line=to_line,
        pallet=to_pallet,
        block=to_block,
    )
    if not to_vi_tri:
        raise HTTPException(status_code=400, detail="Vị trí đích không hợp lệ.")

    try:
        row_count = int(form.get("row_count") or 0)
    except Exception:
        row_count = 0
    ma_cays: list[str] = []
    for i in range(row_count):
        if form.get(f"sel_{i}") in ("on", "true", "1", "yes"):
            ma = (form.get(f"ma_cay_{i}") or "").strip()
            if ma:
                ma_cays.append(ma)
    if not ma_cays:
        raise HTTPException(status_code=400, detail="ChÆ°a chá»n cÃ¢y.")

    transfer_location(db, ma_cays=ma_cays, to_vi_tri=to_vi_tri, note=note)
    db.commit()
    return RedirectResponse(url="/wms/tools/location-transfer?material=fabric&saved=1", status_code=303)


@router.get("/wms/tools/norms", response_class=HTMLResponse)
def tools_norms(request: Request, db: Session = Depends(get_db)):
    q = request.query_params.get("q") or ""
    ma_model = request.query_params.get("ma_model") or ""
    page = request.query_params.get("page") or "1"
    page_size = request.query_params.get("page_size") or "100"

    error = None
    rows = []
    ma_models: list[str] = []
    try:
        ma_models = list_ma_models(db, limit=5000)
        if q:
            rows = search_norms_db(db, q, limit=100)
        else:
            rows = list_norm_rows(
                db,
                ma_model=(ma_model or None),
                page=int(page),
                page_size=int(page_size),
            )
    except Exception as e:
        rows = []
        error = str(e)
    return templates.TemplateResponse(
        request,
        "wms/tools_norms.html",
        {
            "title": "Tra cứu định mức",
            "q": q,
            "ma_model": ma_model,
            "ma_models": ma_models,
            "page": int(page) if str(page).isdigit() else 1,
            "page_size": int(page_size) if str(page_size).isdigit() else 100,
            "rows": rows,
            "error": error,
        },
    )


@router.get("/reports", response_class=HTMLResponse)
def reports_home(request: Request, db: Session = Depends(get_db)):
    view = (request.query_params.get("view") or "ton_kho").strip()
    tab = (request.query_params.get("tab") or "nhu_cau").strip()

    if view == "inbound":
        selected_nhu_cau = (request.query_params.get("nhu_cau") or "").strip()
        selected_status = (request.query_params.get("status") or "").strip()
        nhu_cau_val = selected_nhu_cau or None
        status_val = selected_status if selected_status in {"dang_nhap_kho", "nhap_du"} else None
        groups = inbound_status_by_nhu_cau(db, nhu_cau=nhu_cau_val, status=status_val, limit_lots=8000)
        nhu_cau_options = list_active_inbound_nhu_cau_options(db, status=status_val, limit=5000)

        return templates.TemplateResponse(
            request,
            "reports/index.html",
            {
                "title": "Báo cáo",
                "view": "inbound",
                "tab": tab,
                "inbound_groups": groups,
                "selected_nhu_cau": selected_nhu_cau,
                "selected_status": selected_status,
                "nhu_cau_options": nhu_cau_options,
            },
        )

    if view == "age":
        bucket = (request.query_params.get("bucket") or "").strip()
        nhu_cau = (request.query_params.get("nhu_cau") or "").strip()
        lot = (request.query_params.get("lot") or "").strip()
        sort = (request.query_params.get("sort") or "nearest").strip()

        bucket_val = bucket if bucket in {"under_6m", "over_6m"} else None
        nhu_cau_val = nhu_cau or None
        lot_val = lot or None
        sort_val = sort if sort in {"nearest", "farthest"} else "nearest"

        kpis, roll_rows = ton_kho_by_age_split(
            db,
            limit=8000,
            split_days=183,
            bucket=bucket_val,
            nhu_cau=nhu_cau_val,
            lot=lot_val,
            sort=sort_val,
        )

        # Options for quick-filter UI
        try:
            nc_rows = (
                db.query(LocationAssignment.nhu_cau)
                .filter(LocationAssignment.trang_thai == "Đang lưu")
                .distinct()
                .order_by(LocationAssignment.nhu_cau)
                .all()
            )
            nhu_cau_options = [str(r[0]) for r in nc_rows if r and r[0]]
        except Exception:
            nhu_cau_options = []

        try:
            lot_rows = (
                db.query(LocationAssignment.lot)
                .filter(LocationAssignment.trang_thai == "Đang lưu")
                .distinct()
                .order_by(LocationAssignment.lot)
                .all()
            )
            lot_options = [str(r[0]) for r in lot_rows if r and r[0]]
        except Exception:
            lot_options = []

        return templates.TemplateResponse(
            request,
            "reports/index.html",
            {
                "title": "Báo cáo",
                "view": "age",
                "tab": tab,
                "age_kpis": kpis,
                "age_rows": roll_rows,
                "bucket": bucket_val or "",
                "nhu_cau": nhu_cau,
                "lot": lot,
                "sort": sort_val,
                "nhu_cau_options": nhu_cau_options,
                "lot_options": lot_options,
            },
        )

    col_labels = {
        "nhu_cau": "Nhu cầu",
        "lot": "Lot vải",
        "loai_vai": "Loại vải",
        "mau_vai": "Màu vải",
    }
    handlers = {
        "nhu_cau": ton_kho_by_nhu_cau,
        "lot": ton_kho_by_lot,
        "loai_vai": ton_kho_by_loai_vai,
        "mau_vai": ton_kho_by_mau_vai,
    }
    if tab not in handlers:
        tab = "nhu_cau"

    rows = handlers[tab](db)
    total_so_cay = sum(r.so_cay for r in rows)
    total_tong_yds = sum(r.tong_yds for r in rows)
    total_da_dinh_danh = sum(r.da_dinh_danh for r in rows)
    try:
        stock_nhu_cau_options = [
            str(r[0])
            for r in db.query(LocationAssignment.nhu_cau)
            .filter(LocationAssignment.trang_thai == "Đang lưu")
            .filter(LocationAssignment.nhu_cau.isnot(None))
            .distinct()
            .order_by(LocationAssignment.nhu_cau.asc())
            .all()
            if r and r[0]
        ]
    except Exception:
        stock_nhu_cau_options = []

    return templates.TemplateResponse(
        request,
        "reports/index.html",
        {
            "title": "Báo cáo",
            "view": "ton_kho",
            "tab": tab,
            "col_label": col_labels[tab],
            "rows": rows,
            "total_so_cay": total_so_cay,
            "total_tong_yds": total_tong_yds,
            "total_da_dinh_danh": total_da_dinh_danh,
            "stock_nhu_cau_options": stock_nhu_cau_options,
        },
    )


@router.get("/reports/stock/export")
@router.get("/reports/inbound/export")
def reports_stock_export(
    mode: str = Query(default="selected"),
    nhu_cau: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    export_mode = (mode or "selected").strip().lower()
    if export_mode not in {"selected", "all"}:
        raise HTTPException(status_code=400, detail="Mode export không hợp lệ.")

    nhu_cau_val = (nhu_cau or "").strip() or None
    if export_mode == "selected" and not nhu_cau_val:
        raise HTTPException(status_code=400, detail="Vui lòng chọn Nhu cầu để kết xuất file này.")

    excel_bytes = build_stock_export_excel(
        db,
        nhu_cau=nhu_cau_val,
        export_mode=export_mode,
    )
    suffix = "all_dang_luu" if export_mode == "all" else f"nhu_cau_{nhu_cau_val}"
    safe_suffix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in suffix)
    filename = f"ton_kho_{safe_suffix}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/wms/pallets/{vi_tri}/fragment", response_class=HTMLResponse)
def pallet_rolls_fragment(request: Request, vi_tri: str, db: Session = Depends(get_db)):
    rows = list_pallet_roll_rows(db, vi_tri=vi_tri)
    return templates.TemplateResponse(
        request,
        "wms/_pallet_rolls_fragment.html",
        {"vi_tri": vi_tri, "rows": rows},
    )


@router.get("/wms/gon-blocks/{block}/fragment", response_class=HTMLResponse)
def gon_block_fragment(request: Request, block: str, db: Session = Depends(get_db)):
    rows = list_gon_block_rows(db, block=block)
    return templates.TemplateResponse(
        request,
        "wms/_gon_block_fragment.html",
        {"block": block, "rows": rows},
    )
