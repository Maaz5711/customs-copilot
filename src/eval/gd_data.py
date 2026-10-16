"""Loader for the importer's Goods Declaration extract (Chapter 85, February 2026) in data/raw/importer_data/ (private: gitignored).

The file lists one line per GD item: collectorate, GD type, date, PCT code (a spreadsheet NUMBER, so 8536.909 means 8536.9090), description,
origin, importer identity columns, quantity, unit, values and the duties and taxes that were actually assessed, plus the SRO/schedule columns.
It is real data shared by an importer. NEVER commit the raw file or the identity columns (NTN, importer, consignee, IGM, BL, GD number).
Derived files written to git must be anonymised: use `anon_id` (hash of the GD number) and drop every identity column.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

RAW = Path("data/raw/importer_data/IMP_Ch85_Feb2026.xlsx")

IDENTITY = {"NTN", "IMPORTER", "CONSIGNEE", "IGM", "BL", "GD", "Terminal", "SHIPPING LINE"}


def num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def code8(x) -> str | None:
    """8536.909 -> '85369090'. The spreadsheet kept the code as a number, so trailing zeros after the point were dropped."""
    try:
        s = f"{float(x):.4f}"
    except (TypeError, ValueError):
        return None
    a, b = s.split(".")
    return a.zfill(4) + b if len(a) <= 4 else None


def clean_description(text: str) -> str:
    """Drop the quantity tail the clearing agent types ('QTY 4240 PCS'), keep the product words."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = re.sub(r"\b(QTY|QUANTITY|QYT)\b[:.\s]*[\d,.]+\s*(PCS|PC|SETS?|KGS?|UNITS?|NOS|PAIRS?|MTRS?|METERS?|ROLLS?|CTNS?)?\.?", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .,-")
    return t


def load(path: Path = RAW) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    hdr = list(rows[0])
    body = rows[2:] if list(rows[1]) == hdr else rows[1:]
    out = []
    for r in body:
        d = dict(zip(hdr, r))
        d["code8"] = code8(d.get("PCT"))
        d["anon_id"] = hashlib.sha256(f"gd-{d.get('GD')}".encode()).hexdigest()[:10]
        d["date"] = str(d.get("DATE"))[:10]
        d["desc_clean"] = clean_description(d.get("DESCRIPTION"))
        out.append(d)
    return out
