"""Pack the built data into one zip for upload to a private place (Azure Blob Storage, Google Cloud Storage, any private file link).

    python deploy/pack_data.py                  # writes deploy/out/customs-copilot-data.zip and prints its size and SHA-256

The zip holds data/processed/legal_store.sqlite and data/processed/search_index/ (about 70 MB, derived from FBR documents). It is never committed
(deploy/out/ is ignored). Upload it as a PRIVATE file, make a read-only link to it, and give that link to the server as DATA_ZIP_URL.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed"
OUT = ROOT / "deploy" / "out" / "customs-copilot-data.zip"


def pack(src: pathlib.Path = SRC, out: pathlib.Path = OUT) -> tuple[int, str, int]:
    """Returns (bytes, sha256, files)."""
    files = [src / "legal_store.sqlite", *sorted((src / "search_index").rglob("*"))]
    files = [f for f in files if f.is_file()]
    if not (src / "legal_store.sqlite").exists() or not (src / "search_index" / "tariff" / "emb.npy").exists():
        raise SystemExit("Build the data first: python -m src.store.build and python -m src.search.build")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in files:
            z.write(f, f.relative_to(src).as_posix())
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    return out.stat().st_size, h, len(files)


if __name__ == "__main__":
    size, sha, n = pack()
    print(f"{OUT}\n{n} files, {size / 1e6:.1f} MB\nSHA-256: {sha}")
    sys.exit(0)
