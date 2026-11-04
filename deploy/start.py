"""Start script for any container host (Azure Container Apps, Google Cloud Run, Render, Koyeb, a VM): fetch the private data once, then run the API.

The built data (legal store and search indexes, derived from FBR documents) is not in git or in the image. It is downloaded at start-up from a
PRIVATE place you own. Environment variables (set them in the host's dashboard, as secrets where possible):
    DATA_ZIP_URL       a private link to customs-copilot-data.zip (made by deploy/pack_data.py), for example an Azure Blob SAS URL or a Google
                       signed URL. Treat the link as a password: anyone who has it can download the data.
    DATA_ZIP_SHA256    optional, the zip's SHA-256 (printed by pack_data.py); the download is refused if it does not match
    or DATA_BUCKET     a private Google Cloud Storage bucket holding legal_store.sqlite and search_index/ (optionally under DATA_PREFIX)
    DEEPSEEK_API_KEY   the model key (or another provider's, with LLM_PROVIDER)
    API_MAX_LLM_CALLS  hard cap on model calls for this process (about 5 to 9 per question)
    EXTRA_ALLOWED_HOSTS  optional, the website's domain(s), comma separated
    PORT               set by Cloud Run, Render and similar hosts (default 8080)
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import runpy
import shutil
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
PLATFORM_HOSTS = ["*.azurecontainerapps.io", "*.run.app", "*.onrender.com", "*.koyeb.app", "*.hf.space", "*.fly.dev", "*.up.railway.app"]


def extract_zip(zip_path, dest: pathlib.Path) -> int:
    """Unpack the data zip into `dest`, keeping relative paths. Entries that would land outside `dest` (path tricks) are skipped. Returns the file count."""
    n = 0
    dest = pathlib.Path(dest)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = pathlib.PurePosixPath(info.filename.replace("\\", "/")).parts
            if info.is_dir() or not parts or ".." in parts or parts[0] in ("/", "\\") or ":" in parts[0]:
                continue
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    return n


def download_zip(url: str, dest: pathlib.Path, sha256: str = "") -> int:
    """Stream the zip from `url` to a temporary file, check its SHA-256 when given, unpack it into `dest`. The link itself is never printed."""
    import requests

    h = hashlib.sha256()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        with requests.get(url, stream=True, timeout=(15, 120)) as r:
            r.raise_for_status()
            for chunk in r.iter_content(1 << 20):
                h.update(chunk)
                tmp.write(chunk)
    try:
        if sha256 and h.hexdigest().lower() != sha256.strip().lower():
            raise SystemExit("The downloaded data zip does not match DATA_ZIP_SHA256: refusing to use it.")
        return extract_zip(tmp_path, dest)
    finally:
        os.unlink(tmp_path)


def download_bucket(client, bucket: str, prefix: str, dest: pathlib.Path) -> int:
    """Copy every object under `prefix` of the bucket into `dest`, keeping the relative paths. Returns how many files were copied."""
    prefix = prefix.strip("/")
    n = 0
    for blob in client.list_blobs(bucket, prefix=prefix + "/" if prefix else None):
        rel = blob.name[len(prefix) + 1:] if prefix else blob.name
        if not rel or rel.endswith("/") or ".." in pathlib.PurePosixPath(rel).parts:      # folder placeholders and path tricks are skipped
            continue
        target = dest / pathlib.PurePosixPath(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        n += 1
    return n


def fetch_data() -> None:
    if (DATA / "legal_store.sqlite").exists() and (DATA / "search_index" / "tariff" / "emb.npy").exists():
        return
    if os.environ.get("DATA_ZIP_URL"):
        n = download_zip(os.environ["DATA_ZIP_URL"], DATA, os.environ.get("DATA_ZIP_SHA256", ""))
        print(f"data downloaded and unpacked ({n} files)", flush=True)
    elif os.environ.get("DATA_BUCKET"):
        from google.cloud import storage

        n = download_bucket(storage.Client(), os.environ["DATA_BUCKET"], os.environ.get("DATA_PREFIX", ""), DATA)
        print(f"data downloaded from the bucket ({n} files)", flush=True)
    else:
        raise SystemExit("The built data is missing. Set DATA_ZIP_URL (a private link to the data zip) or DATA_BUCKET (docs/DEPLOY.md).")


def main() -> None:
    fetch_data()
    hosts = [os.environ.get("SPACE_HOST", ""), *os.environ.get("EXTRA_ALLOWED_HOSTS", "").split(","), *PLATFORM_HOSTS, "localhost", "127.0.0.1"]
    os.environ["ALLOWED_HOSTS"] = ",".join(h.strip() for h in hosts if h.strip())
    os.environ.setdefault("API_HOST", "0.0.0.0")
    os.environ["API_PORT"] = os.environ.get("PORT", os.environ.get("API_PORT", "8080"))
    os.environ.setdefault("TRUST_PROXY", "1")
    os.environ.setdefault("API_HSTS", "1")
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    runpy.run_module("src.api", run_name="__main__")


if __name__ == "__main__":
    main()
