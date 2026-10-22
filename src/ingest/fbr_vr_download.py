"""Download FBR Customs valuation rulings (originals) for the precedent index.

Source: the public list behind https://www.fbr.gov.pk/showvaluations (POST /Home/LoadVALUATIONs, department=Customs),
one read-only call that returns every ruling with its title, date and PDF link on download1.fbr.gov.pk.
The PDFs are saved unchanged in data/raw/fbr_valuation_rulings/pdf/ (gitignored originals, never edited).
A manifest (number, title, date, url, file, bytes, sha256) goes to data/processed/vr/manifest.csv.

Polite by design: one request at a time, 1.5 s apart, resumable (files already on disk are skipped).
Only rulings dated from 2022-01-01 are taken by default: the tariff moved to HS 2022 codes in FY2022-23.

    python -m src.ingest.fbr_vr_download                 # list + download (resumes)
    python -m src.ingest.fbr_vr_download --list-only     # refresh the listing only
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fbr_valuation_rulings"
PDF_DIR = RAW / "pdf"
OUT = ROOT / "data" / "processed" / "vr"
LIST_URL = "https://www.fbr.gov.pk/Home/LoadVALUATIONs"
UA = {"User-Agent": "Mozilla/5.0 (customs-copilot research; one request at a time)"}
GAP_S = 1.5


def fetch_listing(path: Path | None = None) -> Path:
    """Save the full listing as returned by FBR (one call)."""
    data = {"draw": "1", "start": "0", "length": "2000", "search[value]": "", "search[regex]": "false",
            "order[0][column]": "2", "order[0][dir]": "desc", "columns[2][data]": "CreationDate", "columns[2][name]": "CreationDate",
            "department": "Customs"}
    r = requests.post(LIST_URL, data=data, headers=UA, timeout=120)
    r.raise_for_status()
    j = r.json()
    if not isinstance(j.get("data"), list) or not j["data"]:
        raise RuntimeError(f"unexpected listing reply: {str(j)[:200]}")
    path = path or RAW / f"listing_{dt.date.today().isoformat()}.json"
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    return path


def latest_listing() -> Path:
    files = sorted(RAW.glob("listing_*.json"))
    if not files:
        raise FileNotFoundError("no listing yet: run with --list-only first")
    return files[-1]


def creation_date(row: dict) -> dt.date:
    ms = int(re.search(r"-?\d+", row["CreationDate"]).group())
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date()


def ruling_ref(row: dict) -> tuple[str, str]:
    """('VR', '2116/2026') from 'Valuation Ruling No. 2116/2026'; kind is VR, PVR (publication ruling), PN, AVR or OTHER."""
    t = re.sub(r"\s+", " ", row.get("VALUATIONNumber") or "").strip()
    m = re.search(r"(\d{1,4})\s*[/-]\s*(20\d\d)", t)
    num = f"{int(m.group(1))}/{m.group(2)}" if m else ""
    low = t.lower()
    kind = ("PVR" if low.startswith("publication") else "AVR" if low.startswith("amendment") else "PN" if "public notice" in low
            else "VR" if "valuation ruling" in low or low.startswith("vr") else "OTHER")
    return kind, num


def select(rows: list[dict], since: dt.date) -> list[dict]:
    out = []
    for r in rows:
        url = (r.get("UploadedFile1") or "").strip()
        if not url.lower().endswith(".pdf") or creation_date(r) < since:
            continue
        out.append(r)
    return out


def download(rows: list[dict], gap: float = GAP_S, limit: int | None = None) -> list[dict]:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.csv"
    done = {}
    if man_path.exists():
        done = {m["file"]: m for m in csv.DictReader(open(man_path, encoding="utf-8"))}
    s = requests.Session()
    s.headers.update(UA)
    fetched = 0
    for r in rows:
        url = r["UploadedFile1"].strip()
        name = url.rsplit("/", 1)[1]
        dest = PDF_DIR / name
        kind, num = ruling_ref(r)
        rec = {"valuation_id": r.get("VALUATIONID"), "kind": kind, "number": num, "label": re.sub(r"\s+", " ", r.get("VALUATIONNumber") or "").strip(),
               "title": re.sub(r"\s+", " ", r.get("Title") or "").strip(), "date": creation_date(r).isoformat(), "url": url, "file": name}
        if dest.exists() and dest.stat().st_size > 1000 and name in done:
            continue
        if limit is not None and fetched >= limit:
            break
        for attempt in range(3):
            try:
                resp = s.get(url, timeout=120)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                    dest.write_bytes(resp.content)
                    rec.update(bytes=len(resp.content), sha256=hashlib.sha256(resp.content).hexdigest(), status="ok")
                else:
                    rec.update(bytes=len(resp.content), sha256="", status=f"http {resp.status_code} / not a pdf")
                break
            except requests.RequestException as e:
                rec.update(bytes=0, sha256="", status=f"error {type(e).__name__}")
                time.sleep(5 * (attempt + 1))
        rec["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        done[name] = rec
        fetched += 1
        if fetched % 20 == 0:
            _write_manifest(man_path, done)
            print(f"{fetched} fetched, last {rec['label']} ({rec.get('bytes', 0) // 1024} KB, {rec['status']})", flush=True)
        time.sleep(gap)
    # files already on disk from an earlier run without a manifest row
    for r in rows:
        name = r["UploadedFile1"].strip().rsplit("/", 1)[1]
        dest = PDF_DIR / name
        if name not in done and dest.exists():
            b = dest.read_bytes()
            kind, num = ruling_ref(r)
            done[name] = {"valuation_id": r.get("VALUATIONID"), "kind": kind, "number": num, "label": re.sub(r"\s+", " ", r.get("VALUATIONNumber") or "").strip(),
                          "title": re.sub(r"\s+", " ", r.get("Title") or "").strip(), "date": creation_date(r).isoformat(), "url": r["UploadedFile1"].strip(),
                          "file": name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "status": "ok", "fetched_at": ""}
    _write_manifest(man_path, done)
    return list(done.values())


FIELDS = ["valuation_id", "kind", "number", "label", "title", "date", "url", "file", "bytes", "sha256", "status", "fetched_at"]


def _write_manifest(path: Path, done: dict) -> None:
    rows = sorted(done.values(), key=lambda m: (m.get("date") or "", m.get("file")), reverse=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--since", default="2022-01-01")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.list_only:
        print(fetch_listing())
        return
    rows = json.loads(latest_listing().read_text(encoding="utf-8"))["data"]
    sel = select(rows, dt.date.fromisoformat(a.since))
    print(f"{len(sel)} rulings since {a.since} (of {len(rows)} listed)", flush=True)
    man = download(sel, limit=a.limit)
    ok = [m for m in man if m.get("status") == "ok"]
    print(f"done: {len(ok)} PDFs, {sum(int(m.get('bytes') or 0) for m in ok) // (1024 * 1024)} MB; failures {len(man) - len(ok)}")


if __name__ == "__main__":
    main()
