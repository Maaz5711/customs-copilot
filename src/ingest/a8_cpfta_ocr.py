"""A8: read the scanned SRO 1640(I)/2019 (China-Pakistan FTA Phase II tariff schedule) with a local OCR engine.

The PDF has no text layer: every page is a scanned picture of one table (Sr.No, PCT code, description, then the
customs duty for Year 1 to Year 15, 1-Jan-2020 to 1-Jan-2034). We render each page, straighten it (the scans are slightly
tilted), run RapidOCR (PP-OCR models on onnxruntime, runs on this PC, no paid service) and keep every text box with its
position. Nothing is interpreted here. The row builder and the validators are in a8_cpfta.py.
Outputs: data/processed/cpfta_ocr/p<NNN>.json (cached; reruns skip finished pages).
Usage: python -m src.ingest.a8_cpfta_ocr [first_page last_page] [dpi]
"""
from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pymupdf

PDF = glob.glob("data/raw/cpfta/*.pdf")[0]
OUT = Path("data/processed/cpfta_ocr")
DPI = 200


def render(doc, pno: int, dpi: int = DPI) -> np.ndarray:
    pix = doc[pno - 1].get_pixmap(dpi=dpi)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()


def estimate_skew(img: np.ndarray) -> float:
    """Tilt in degrees (positive = text runs downhill to the right), by maximising the row-profile sharpness."""
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    bw = (small < 140).astype(np.uint8)
    best, best_a = -1.0, 0.0
    h, w = bw.shape
    for a in np.arange(-1.5, 1.51, 0.05):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        r = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST)
        s = float(np.var(r.sum(axis=1)))
        if s > best:
            best, best_a = s, float(a)
    return best_a


def deskew(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def read_page(doc, pno: int, ocr, dpi: int = DPI) -> dict:
    img = render(doc, pno, dpi)
    ang = estimate_skew(img)
    img2 = deskew(img, ang)
    t = time.time()
    res, _ = ocr(img2)
    toks = []
    for box, text, conf in res or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        toks.append({"x0": round(min(xs), 1), "x1": round(max(xs), 1), "y0": round(min(ys), 1), "y1": round(max(ys), 1),
                     "text": text, "conf": round(float(conf), 3)})
    return {"page": pno, "dpi": dpi, "skew_deg": round(ang, 2), "width": img2.shape[1], "height": img2.shape[0],
            "seconds": round(time.time() - t, 1), "tokens": toks, "engine": "rapidocr-onnxruntime 1.2.3 (PP-OCR)"}


def main(first=1, last=None, dpi=DPI):
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    doc = pymupdf.open(PDF)
    last = last or len(doc)
    OUT.mkdir(parents=True, exist_ok=True)
    for pno in range(first, last + 1):
        f = OUT / f"p{pno:03d}.json"
        if f.exists():
            continue
        d = read_page(doc, pno, ocr, dpi)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        print(pno, d["skew_deg"], len(d["tokens"]), d["seconds"], flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 1, int(a[1]) if len(a) > 1 else None, int(a[2]) if len(a) > 2 else DPI)
