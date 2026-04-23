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

_COL_W = [45 * mm, 55 * mm, 38 * mm]
_ROW_H = [16 * mm, 14 * mm, 12 * mm, 14 * mm, 26 * mm, 22 * mm, 34 * mm]
_PAD_LR = 12.0
_PAD_TB = 8.0


def _avail_w(col: int, span: int = 1) -> float:
    return sum(_COL_W[col : col + span]) - _PAD_LR


def _avail_h(row: int) -> float:
    return _ROW_H[row] - _PAD_TB


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
    candidates = [
        ("TimesNewRoman", r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
        ("Arial", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    for name, normal, bold in candidates:
        got = _try_register_font(name, normal, bold)
        if got:
            return got
    return "Helvetica", "Helvetica-Bold"


def _shrink_to_fit(
    text: str,
    style: ParagraphStyle,
    avail_w: float,
    avail_h: float,
    min_size: float = 7.0,
) -> Paragraph:
    """Return a Paragraph that fits avail_w × avail_h, shrinking font size if needed."""
    s = (text or "").replace("\n", "<br/>")
    size = style.fontSize
    while size >= min_size:
        sz_style = ParagraphStyle(
            "_fit",
            parent=style,
            fontSize=size,
            leading=max(size * 1.15, size + 1.0),
        )
        p = Paragraph(s, sz_style)
        _, h = p.wrap(avail_w, 99999)
        if h <= avail_h:
            return p
        size -= 0.5
    fb = ParagraphStyle("_fit_min", parent=style, fontSize=min_size, leading=min_size + 1.0)
    return Paragraph(s, fb)


def _merge_tag_fields(tags: list[HangingTag]) -> dict:
    def uniq_join(vals, sep: str = " / ") -> str:
        seen: list[str] = []
        for v in vals:
            s = (v or "").strip()
            if s and s not in seen:
                seen.append(s)
        return sep.join(seen)

    return {
        "khach_hang": (tags[0].khach_hang or "DECATHLON").strip() or "DECATHLON",
        "nha_cung_cap": uniq_join(t.nha_cung_cap for t in tags),
        "ngay_nhap_hang": min((t.ngay_nhap_hang for t in tags if t.ngay_nhap_hang), default=None),
        "ma_hang": uniq_join(t.ma_hang for t in tags),
        "nhu_cau": uniq_join(t.nhu_cau for t in tags),
        "loai_vai": uniq_join(t.loai_vai for t in tags),
        "ma_art": uniq_join(t.ma_art for t in tags),
        "mau_vai": uniq_join(t.mau_vai for t in tags),
        "ma_mau": uniq_join(t.ma_mau for t in tags),
        "lot": uniq_join(t.lot for t in tags),
        "ket_qua_kiem_tra": tags[0].ket_qua_kiem_tra if tags else "OK",
    }


def _render_tag_pdf(fields: dict, doc_title: str = "Bang treo") -> bytes:
    buf = BytesIO()
    page_size = (138 * mm, 195 * mm)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=0,
        rightMargin=0,
        topMargin=0,
        bottomMargin=0,
        title=doc_title,
    )

    base_styles = getSampleStyleSheet()
    font_normal, font_bold = _get_fonts()

    title_style = ParagraphStyle(
        "bt_title",
        parent=base_styles["Title"],
        fontName=font_bold,
        fontSize=16,
        alignment=1,
        spaceAfter=0,
        spaceBefore=0,
    )
    label_style = ParagraphStyle(
        "bt_label",
        parent=base_styles["Normal"],
        fontName=font_bold,
        fontSize=10,
        leading=12,
        alignment=1,
    )
    value_style = ParagraphStyle(
        "bt_value",
        parent=base_styles["Normal"],
        fontName=font_normal,
        fontSize=16,
        leading=18,
        alignment=0,
    )
    value_bold_style = ParagraphStyle("bt_value_bold", parent=value_style, fontName=font_bold)
    value_center_style = ParagraphStyle("bt_value_center", parent=value_style, alignment=1)
    value_center_bold_style = ParagraphStyle("bt_value_center_bold", parent=value_center_style, fontName=font_bold)
    lot_style = ParagraphStyle(
        "bt_lot",
        parent=value_center_bold_style,
        fontSize=28,
        leading=30,
    )

    def L(text: str) -> Paragraph:
        return Paragraph(text, label_style)

    def _v(text: str, row: int, col: int, span: int = 1, *, bold: bool = False, center: bool = False) -> Paragraph:
        s = (
            value_center_bold_style if center and bold
            else value_center_style if center
            else value_bold_style if bold
            else value_style
        )
        return _shrink_to_fit(text or "", s, _avail_w(col, span), _avail_h(row))

    def _lot(text: str) -> Paragraph:
        return _shrink_to_fit(text or "", lot_style, _avail_w(1, 2), _avail_h(6))

    story: list[object] = []
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(fields["khach_hang"], title_style))
    story.append(Spacer(1, 2 * mm))

    rows = [
        [L("NHÀ CUNG CẤP<br/>(Supplier)"), _v(fields["nha_cung_cap"], 0, 1, 2, bold=True), ""],
        [L("NGÀY NHẬP HÀNG<br/>(Date of import)"), _v(_d(fields["ngay_nhap_hang"]), 1, 1, 2, bold=True), ""],
        [L("MÃ HÀNG"), _v(fields["ma_hang"], 2, 1, 2, bold=True), ""],
        [L("NHU CẦU NGUYÊN LIỆU"), _v(fields["nhu_cau"], 3, 1, 2, bold=True, center=True), ""],
        [
            L("LOẠI VẢI - MÃ VẢI<br/>(Description - Model)"),
            _v(fields["loai_vai"], 4, 1, bold=True),
            _v(fields["ma_art"], 4, 2, bold=True, center=True),
        ],
        [
            L("MÀU - MÃ MÀU<br/>(Color - Item)"),
            _v(fields["mau_vai"], 5, 1, bold=True),
            _v(fields["ma_mau"], 5, 2, bold=True, center=True),
        ],
        [L("LOT:"), _lot(fields["lot"]), ""],
    ]

    tbl = Table(rows, colWidths=_COL_W, rowHeights=_ROW_H)
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


def render_hanging_tag_pdf(tag: HangingTag) -> bytes:
    return _render_tag_pdf(_merge_tag_fields([tag]), doc_title=f"Bang treo {tag.id}")


def render_merged_hanging_tag_pdf(tags: list[HangingTag]) -> bytes:
    ids_str = "_".join(str(t.id) for t in tags[:5])
    return _render_tag_pdf(_merge_tag_fields(tags), doc_title=f"Gop bang treo {ids_str}")
