from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fabric_warehouse.db.models.receipt import Receipt, ReceiptLine


def render_receipt_pdf(receipt: Receipt, lines: list[ReceiptLine]) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
        title=f"Receipt {receipt.id}",
    )

    styles = getSampleStyleSheet()
    story: list[object] = []

    title = f"Phiếu nhập kho (Import) — #{receipt.id}"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 8))

    meta = [
        ["Nguồn file", receipt.source_filename],
        ["Ngày", receipt.receipt_date.isoformat() if receipt.receipt_date else ""],
        ["Ghi chú", receipt.note or ""],
        ["Số dòng", str(len(lines))],
    ]
    meta_tbl = Table(meta, colWidths=[90, 420])
    meta_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 12))

    data = [["Mã cây", "Nhu cầu", "Lot", "Ánh màu", "Model", "Art", "YDS"]]
    for ln in lines:
        yds = ""
        if ln.yards is not None:
            try:
                yds = f"{float(ln.yards):.2f}"
            except Exception:
                yds = str(ln.yards)
        data.append(
            [
                ln.ma_cay,
                ln.nhu_cau or "",
                ln.lot or "",
                ln.anh_mau or "",
                ln.model or "",
                ln.art or "",
                yds,
            ]
        )

    tbl = Table(data, repeatRows=1, colWidths=[75, 65, 55, 60, 60, 60, 45])
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(tbl)

    doc.build(story)
    return buf.getvalue()

