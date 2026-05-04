from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s.replace(" ", "")


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    s = str(value).strip()
    return s or None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_date_from_text(text: str) -> date | None:
    # Support common formats found in "phiếu": dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd.
    patterns = [
        r"(?P<d>\d{1,2})[\/\-](?P<m>\d{1,2})[\/\-](?P<y>\d{4})",
        r"(?P<y>\d{4})[\/\-](?P<m>\d{1,2})[\/\-](?P<d>\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        try:
            y = int(m.group("y"))
            mm = int(m.group("m"))
            dd = int(m.group("d"))
            return date(y, mm, dd)
        except Exception:
            continue
    return None


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    # numpy scalar -> python scalar
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            pass
    return value


@dataclass(frozen=True)
class ParsedReceipt:
    source_filename: str
    receipt_date: date | None
    rows: list[dict[str, Any]]
    warnings: list[str]


_COLUMN_ALIASES: dict[str, list[str]] = {
    "ma_cay": ["macay", "macayvai", "barcode", "idcay", "ma cay", "mã cây", "mãcây"],
    "nhu_cau": ["nhucau", "nhu cau", "nhu cầu"],
    "lot": ["lot", "lo", "lô"],
    "anh_mau": ["anhmau", "anh mau", "ánh màu", "mau", "màu"],
    "model": ["model", "mamodel", "ma model", "mã model"],
    "art": ["art", "maart", "ma art", "mã art"],
    "yards": ["yds", "yards", "yard", "soluong", "số lượng", "qty"],
    "phieu_xuat": ["phieuxuat", "phiếu xuất", "phieu xuat", "phieu"],
}


def parse_receipt_excel(
    content: bytes,
    *,
    source_filename: str,
    header_row: int | None = None,
    sheet_name: str | None = None,
) -> ParsedReceipt:
    warnings: list[str] = []

    bio = BytesIO(content)
    xl = pd.ExcelFile(bio, engine="openpyxl")

    selected_sheet = sheet_name
    selected_header_row = header_row

    def detect_header_row(sheet: str) -> int | None:
        preview = pd.read_excel(bio, sheet_name=sheet, header=None, nrows=40, engine="openpyxl")
        for i in range(len(preview)):
            row_vals = [_norm(str(v)) for v in preview.iloc[i].tolist()]
            if "macay" in row_vals:
                return i
        return None

    if not selected_sheet:
        for s in xl.sheet_names:
            hr = detect_header_row(s)
            if hr is not None:
                selected_sheet = s
                selected_header_row = hr if selected_header_row is None else selected_header_row
                break
        if not selected_sheet:
            selected_sheet = xl.sheet_names[0]
            warnings.append("Không tự phát hiện được sheet có 'Mã cây' — dùng sheet đầu tiên.")

    if selected_header_row is None:
        selected_header_row = detect_header_row(selected_sheet) or 0
        warnings.append(f"Tự phát hiện header ở dòng {selected_header_row + 1}.")

    warnings.append(f"Đọc sheet: {selected_sheet} (header dòng {selected_header_row + 1}).")

    df = pd.read_excel(
        bio,
        sheet_name=selected_sheet,
        header=selected_header_row,
        engine="openpyxl",
    )
    df = df.dropna(how="all")
    if df.empty:
        return ParsedReceipt(source_filename=source_filename, receipt_date=None, rows=[], warnings=["Excel rỗng."])

    original_columns = [str(c) for c in df.columns]
    norm_to_col: dict[str, str] = {_norm(c): str(c) for c in original_columns}

    def find_col(key: str) -> str | None:
        for alias in _COLUMN_ALIASES.get(key, []):
            col = norm_to_col.get(_norm(alias))
            if col:
                return col
        if key in {"art", "model"}:
            return None
        # fallback: partial contains match
        want = {_norm(a) for a in _COLUMN_ALIASES.get(key, [])}
        for nc, col in norm_to_col.items():
            if any(w in nc for w in want):
                return col
        return None

    col_ma_cay = find_col("ma_cay")
    if not col_ma_cay:
        raise ValueError("Không tìm thấy cột 'Mã cây' trong file Excel.")

    col_nhu_cau = find_col("nhu_cau")
    col_lot = find_col("lot")
    col_anh_mau = find_col("anh_mau")
    col_model = find_col("model")
    col_art = find_col("art")
    col_yards = find_col("yards")
    col_phieu_xuat = find_col("phieu_xuat")

    if col_phieu_xuat:
        df[col_phieu_xuat] = df[col_phieu_xuat].ffill()

    if col_anh_mau:
        df[col_anh_mau] = df[col_anh_mau].fillna("CHUNG")

    # Drop duplicates by "Mã cây" (keep first) to mimic legacy behavior.
    df = df.drop_duplicates(subset=[col_ma_cay], keep="first")

    receipt_date: date | None = None
    if col_phieu_xuat:
        for v in df[col_phieu_xuat].dropna().astype(str).tolist():
            v = v.strip()
            if not v:
                continue
            receipt_date = _extract_date_from_text(v)
            if receipt_date:
                break
        if not receipt_date:
            warnings.append("Không suy ra được ngày từ cột 'Phiếu xuất'.")
    else:
        warnings.append("Không có cột 'Phiếu xuất' để suy ra ngày.")

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        ma_cay = _coerce_str(r.get(col_ma_cay))
        if not ma_cay:
            continue
        lot_value = _coerce_str(r.get(col_lot)) if col_lot else None
        # Skip summary/header-like rows that don't carry lot (common in reports).
        if not lot_value:
            continue
        row: dict[str, Any] = {
            "ma_cay": ma_cay,
            "nhu_cau": _coerce_str(r.get(col_nhu_cau)) if col_nhu_cau else None,
            "lot": lot_value,
            "anh_mau": _coerce_str(r.get(col_anh_mau)) if col_anh_mau else "CHUNG",
            "model": _coerce_str(r.get(col_model)) if col_model else None,
            "art": _coerce_str(r.get(col_art)) if col_art else None,
            "yards": _coerce_float(r.get(col_yards)) if col_yards else None,
            "raw_data": {str(k): _to_jsonable(v) for k, v in r.to_dict().items()},
        }
        rows.append(row)

    if not rows:
        warnings.append("Không trích được dòng dữ liệu hợp lệ (thiếu Mã cây).")

    return ParsedReceipt(
        source_filename=source_filename,
        receipt_date=receipt_date,
        rows=rows,
        warnings=warnings,
    )
