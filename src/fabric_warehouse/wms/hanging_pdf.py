from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fabric_warehouse.db.models.hanging_tag import HangingTag


def _d(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _try_register_font(font_name: str, normal_path: str, bold_path: str) -> tuple[str, str] | None:
    try:
        pdfmetrics.registerFont(TTFont(font_name, normal_path))
        pdfmetrics.registerFont(TTFont(f"{font_name}-Bold", bold_path))
        return font_name, f"{font_name}-Bold"
    except Exception:
        return None


def _get_fonts() -> tuple[str, str]:
    """
    Prefer Windows fonts that support Vietnamese to avoid broken diacritics.
    """
    candidates = [
        ("TimesNewRoman", r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
        ("Arial", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    for name, normal, bold in candidates:
        got = _try_register_font(name, normal, bold)
        if got:
            return got
    return "Helvetica", "Helvetica-Bold"


def render_hanging_tag_pdf(tag: HangingTag) -> bytes:
    """
    Render "bảng treo" similar to legacy Streamlit HTML print format.
    """
    buf = BytesIO()

    # Match legacy "bảng treo" size closely (138mm x 195mm).
    page_size = (138 * mm, 195 * mm)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=0,
        rightMargin=0,
        topMargin=0,
        bottomMargin=0,
        title=f"Bang treo {tag.id}",
    )

    base_styles = getSampleStyleSheet()
    font_normal, font_bold = _get_fonts()

    title_style = ParagraphStyle(
        "bt_title",
        parent=base_styles["Title"],
        fontName=font_bold,
        fontSize=18,
        alignment=1,  # center
        spaceAfter=0,
        spaceBefore=0,
    )
    label_style = ParagraphStyle(
        "bt_label",
        parent=base_styles["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=11,
        alignment=1,  # center
    )
    value_style = ParagraphStyle(
        "bt_value",
        parent=base_styles["Normal"],
        fontName=font_normal,
        fontSize=14,
        leading=16,
        alignment=0,  # left
    )
    value_bold_style = ParagraphStyle("bt_value_bold", parent=value_style, fontName=font_bold)
    value_center_style = ParagraphStyle("bt_value_center", parent=value_style, alignment=1)
    value_center_bold_style = ParagraphStyle("bt_value_center_bold", parent=value_center_style, fontName=font_bold)
    lot_style = ParagraphStyle(
        "bt_lot",
        parent=value_center_bold_style,
        fontSize=22,
        leading=24,
    )

    def L(text: str) -> Paragraph:
        return Paragraph(text, label_style)

    def V(text: str, *, bold: bool = False, center: bool = False) -> Paragraph:
        s = (text or "").strip()
        style = value_style
        if center and bold:
            style = value_center_bold_style
        elif center:
            style = value_center_style
        elif bold:
            style = value_bold_style
        return Paragraph(s.replace("\n", "<br/>"), style)

    def LOT(text: str) -> Paragraph:
        return Paragraph((text or "").strip(), lot_style)

    story: list[object] = []
    title = (tag.khach_hang or "DECATHLON").strip() or "DECATHLON"
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 4 * mm))

    rows = [
        [L("NHÀ CUNG CẤP<br/>(Supplier)"), V(tag.nha_cung_cap or "", bold=True), ""],
        [L("NGÀY NHẬP HÀNG<br/>(Date of import)"), V(_d(tag.ngay_nhap_hang), bold=True), ""],
        [L("MÃ HÀNG"), V(tag.ma_hang or "", bold=True), ""],
        [L("NHU CẦU NGUYÊN LIỆU"), V(tag.nhu_cau or "", bold=True, center=True), ""],
        [
            L("LOẠI VẢI - MÃ VẢI<br/>(Description - Model)"),
            V(tag.loai_vai or ""),
            V(tag.ma_art or "", bold=True, center=True),
        ],
        [
            L("MÀU - MÃ MÀU<br/>(Color - Item)"),
            V(tag.mau_vai or ""),
            V(tag.ma_mau or "", bold=True, center=True),
        ],
        [L("LOT:"), LOT(tag.lot or ""), ""],
        [
            L("KẾT QUẢ KIỂM TRA<br/>(Result of check)"),
            V("ĐẠT<br/>(Pass)", bold=True, center=True),
            V(tag.ket_qua_kiem_tra or "OK", bold=True, center=True),
        ],
    ]

    tbl = Table(
        rows,
        colWidths=[45 * mm, 55 * mm, 38 * mm],
        rowHeights=[16 * mm, 14 * mm, 12 * mm, 14 * mm, 26 * mm, 22 * mm, 18 * mm, 18 * mm],
    )
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
                ("SPAN", (1, 0), (2, 0)),
                ("SPAN", (1, 1), (2, 1)),
                ("SPAN", (1, 2), (2, 2)),
                ("SPAN", (1, 3), (2, 3)),
                ("SPAN", (1, 6), (2, 6)),
                ("ALIGN", (1, 6), (2, 6), "CENTER"),
                ("ALIGN", (1, 7), (2, 7), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()

