from __future__ import annotations

from io import BytesIO

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from fabric_warehouse.db.session import get_db
from fabric_warehouse.wms.hanging_pdf import render_hanging_tag_pdf, render_merged_hanging_tag_pdf
from fabric_warehouse.wms.hanging_service import backfill_hanging_tags, fill_missing_hanging_fields
from fabric_warehouse.wms.pdf import render_receipt_pdf
from fabric_warehouse.wms.receipts_service import (
    get_receipt,
    get_receipt_lines,
    import_receipt_from_excel,
    list_receipts,
)
from fabric_warehouse.db.models.hanging_tag import HangingTag
from fabric_warehouse.wms.stock_check_service import (
    get_roll_rows,
    list_lot_options,
    list_nhu_cau_options,
    upsert_stock_checks,
)
from fabric_warehouse.wms.location_service import (
    assign_location,
    line_options,
    list_anh_mau_options,
    list_lot_options_for_location,
    list_nhu_cau_options_for_location,
    list_rolls_for_location,
    pallet_options,
    tang_options,
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
from fabric_warehouse.web.jinja_filters import fmt_gmt7
from fabric_warehouse.config import settings
from fabric_warehouse.db.models.user import User

templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader("src/fabric_warehouse/web/templates", encoding="utf-8"),
        autoescape=select_autoescape(["html", "xml"]),
    )
)
templates.env.filters["gmt7"] = fmt_gmt7

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
    return templates.TemplateResponse(
        request,
        "wms/receipts.html",
        {"title": "Phiếu nhập kho", "receipts": receipts},
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
    nhu_cau: str | None = request.query_params.get("nhu_cau")
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
        if nhu_cau:
            q = q.filter(HangingTag.nhu_cau == nhu_cau)
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
            "tags": tags,
            "error": error,
            "nhu_cau": nhu_cau,
            "nhu_cau_options": nhu_cau_options,
        },
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
        lot=_uniq_join(t.lot for t in tags),
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
    nhu_cau: str | None = None,
):
    if ids:
        tags = db.query(HangingTag).filter(HangingTag.id.in_(ids)).order_by(HangingTag.id.asc()).all()
    elif nhu_cau:
        tags = (
            db.query(HangingTag)
            .filter(HangingTag.nhu_cau == nhu_cau)
            .order_by(HangingTag.lot.asc(), HangingTag.id.asc())
            .all()
        )
    else:
        tags = []

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
    nhu_cau = request.query_params.get("nhu_cau")
    return templates.TemplateResponse(
        request,
        "wms/hanging_edit.html",
        {"title": f"Sửa bảng treo #{tag.id}", "tag": tag, "nhu_cau": nhu_cau},
    )


@router.get("/wms/hanging/{tag_id}/edit/fragment", response_class=HTMLResponse)
def hanging_edit_fragment(request: Request, tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(HangingTag).filter(HangingTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bảng treo.")
    nhu_cau = request.query_params.get("nhu_cau")
    return templates.TemplateResponse(
        request,
        "wms/_hanging_edit_fragment.html",
        {"tag": tag, "nhu_cau": nhu_cau},
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

    nhu_cau = request.query_params.get("nhu_cau")
    url = "/wms/hanging"
    if nhu_cau:
        url = f"/wms/hanging?nhu_cau={nhu_cau}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/wms/stock", response_class=HTMLResponse)
def stock_check_home(request: Request, db: Session = Depends(get_db)):
    nhu_cau = request.query_params.get("nhu_cau")
    lot = request.query_params.get("lot")

    nhu_cau_options = list_nhu_cau_options(db)
    lot_options = list_lot_options(db, nhu_cau=nhu_cau) if nhu_cau else []
    # If user is viewing a completed lot via query params (e.g., after save redirect),
    # keep it in the dropdown so the selection stays visible.
    if lot and lot not in lot_options:
        lot_options = [lot, *lot_options]

    rows = get_roll_rows(db, nhu_cau=nhu_cau, lot=lot) if (nhu_cau and lot) else []
    return templates.TemplateResponse(
        request,
        "wms/stock_check.html",
        {
            "title": "Nhập kho / kiểm kho",
            "nhu_cau": nhu_cau,
            "lot": lot,
            "nhu_cau_options": nhu_cau_options,
            "lot_options": lot_options,
            "rows": rows,
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

    return RedirectResponse(url=f"/wms/stock?nhu_cau={nhu_cau}&lot={lot}&saved=1", status_code=303)


@router.get("/wms/stock/locations", response_class=HTMLResponse)
def location_home(request: Request, db: Session = Depends(get_db)):
    nhu_cau = request.query_params.get("nhu_cau")
    anh_mau = request.query_params.get("anh_mau")
    lot = request.query_params.get("lot")

    nhu_cau_options = list_nhu_cau_options_for_location(db)
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
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
        },
    )


@router.post("/wms/stock/locations")
async def location_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    nhu_cau = (form.get("nhu_cau") or "").strip()
    anh_mau = (form.get("anh_mau") or "").strip() or None
    lot = (form.get("lot") or "").strip()
    tang = (form.get("tang") or "").strip()
    line = (form.get("line") or "").strip()
    pallet = (form.get("pallet") or "").strip()
    if not nhu_cau or not lot or not tang or not line or not pallet:
        raise HTTPException(status_code=400, detail="Thiáº¿u thÃ´ng tin lá»c hoáº·c vá»‹ trÃ­.")
    vi_tri = f"{tang}.{line}.{pallet}"

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
    nhu_cau = request.query_params.get("nhu_cau")
    lot = request.query_params.get("lot")
    tab = request.query_params.get("tab") or "issue"

    nhu_cau_options = list_issue_nhu_cau_options(db)
    lot_options = list_issue_lot_options(db, nhu_cau=nhu_cau) if nhu_cau else []
    if lot and lot not in lot_options:
        lot_options = [lot, *lot_options]

    candidates = list_issue_candidates(db, nhu_cau=nhu_cau, lot=lot) if (tab == "issue" and nhu_cau and lot) else []

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
    issues = list_issue_history(db, date_from=df, date_to=dt) if tab == "history" else []
    counts = count_issue_lines(db, issue_ids=[i.id for i in issues]) if issues else {}

    return templates.TemplateResponse(
        request,
        "wms/issue.html",
        {
            "title": "Xuất kho",
            "tab": tab,
            "nhu_cau": nhu_cau,
            "lot": lot,
            "nhu_cau_options": nhu_cau_options,
            "lot_options": lot_options,
            "candidates": candidates,
            "issues": issues,
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
    return RedirectResponse(url=f"/wms/issue?nhu_cau={nhu_cau}&lot={lot}&saved=1#issue", status_code=303)


@router.get("/wms/stock/returns", response_class=HTMLResponse)
def returns_home(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get("tab") or "todo"

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

    candidates = list_return_candidates(db) if tab == "todo" else []
    history = list_return_history(db, date_from=df, date_to=dt) if tab == "history" else []

    return templates.TemplateResponse(
        request,
        "wms/returns.html",
        {
            "title": "Tái nhập kho",
            "tab": tab,
            "candidates": candidates,
            "history": history,
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
        },
    )


@router.post("/wms/stock/returns")
async def returns_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    issue_line_id = int(form.get("issue_line_id") or 0)
    ma_cay = (form.get("ma_cay") or "").strip()
    ngay_s = (form.get("ngay_tai_nhap") or "").strip()
    status = (form.get("status") or "").strip() or "TÃ¡i nháº­p kho"
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
        raise HTTPException(status_code=400, detail="Thiáº¿u dá»¯ liá»‡u.")
    try:
        ngay_tai_nhap = date.fromisoformat(ngay_s)
    except Exception as e:
        raise HTTPException(status_code=400, detail="NgÃ y tÃ¡i nháº­p khÃ´ng há»£p lá»‡.") from e

    vi_tri_moi = None
    if status == "TÃ¡i nháº­p kho":
        tang = (form.get("tang") or "").strip()
        line = (form.get("line") or "").strip()
        pallet = (form.get("pallet") or "").strip()
        if not tang or not line or not pallet:
            raise HTTPException(status_code=400, detail="Thiáº¿u vá»‹ trÃ­ má»›i.")
        vi_tri_moi = f"{tang}.{line}.{pallet}"

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


@router.get("/wms/tools/trace", response_class=HTMLResponse)
def tools_trace(request: Request, db: Session = Depends(get_db)):
    lot = request.query_params.get("lot") or ""
    ma_cay = request.query_params.get("ma_cay") or ""
    lot_options = list_trace_lots(db, limit=2000)
    ma_cay_options = list_trace_ma_cays(db, lot=lot, limit=5000) if lot else []
    events = build_trace_timeline(db, lot=lot, ma_cay=ma_cay) if (lot and ma_cay) else []
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
    tang = request.query_params.get("tang") or "A"
    line = request.query_params.get("line") or "01"
    pallet = request.query_params.get("pallet") or "01"
    vi_tri = f"{tang}.{line}.{pallet}"

    from fabric_warehouse.db.models.location_assignment import LocationAssignment

    rows = (
        db.query(LocationAssignment)
        .filter(LocationAssignment.vi_tri == vi_tri)
        .filter(LocationAssignment.trang_thai == "Äang lÆ°u")
        .order_by(LocationAssignment.ma_cay.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "wms/tools_location_transfer.html",
        {
            "title": "Điều chuyển vị trí",
            "tang": tang,
            "line": line,
            "pallet": pallet,
            "vi_tri": vi_tri,
            "rows": rows,
            "tang_options": tang_options(),
            "line_options": line_options(),
            "pallet_options": pallet_options(),
        },
    )


@router.post("/wms/tools/location-transfer")
async def tools_location_transfer_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    to_tang = (form.get("to_tang") or "").strip()
    to_line = (form.get("to_line") or "").strip()
    to_pallet = (form.get("to_pallet") or "").strip()
    note = (form.get("note") or "").strip() or None
    to_vi_tri = f"{to_tang}.{to_line}.{to_pallet}"

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
    return RedirectResponse(url="/wms/tools/location-transfer?saved=1", status_code=303)


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


@router.get("/wms/pallets/{vi_tri}/fragment", response_class=HTMLResponse)
def pallet_rolls_fragment(request: Request, vi_tri: str, db: Session = Depends(get_db)):
    rows = list_pallet_roll_rows(db, vi_tri=vi_tri)
    return templates.TemplateResponse(
        request,
        "wms/_pallet_rolls_fragment.html",
        {"vi_tri": vi_tri, "rows": rows},
    )

