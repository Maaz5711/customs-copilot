"""Start script for any container host (Google Cloud Run, Render, Koyeb, Hugging Face Space, a VM): fetch the private data once, then run the API.

The built data (legal store and search indexes, derived from FBR documents) is not in git or in the image. It is downloaded at start-up from a
PRIVATE Google Cloud Storage bucket in your own account. Environment variables (set them in the host's dashboard):
    DATA_BUCKET        the bucket holding legal_store.sqlite and search_index/ (Cloud Run reads it with its own service account,
                       so no key is needed), optionally under DATA_PREFIX
    DEEPSEEK_API_KEY   the model key (or another provider's, with LLM_PROVIDER)
    API_MAX_LLM_CALLS  hard cap on model calls for this process (about 5 to 9 per question)
    EXTRA_ALLOWED_HOSTS  optional, the website's domain(s), comma separated
    PORT               set by Cloud Run, Render and similar hosts (default 8080)
"""
from __future__ import annotations

import os
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
PLATFORM_HOSTS = ["*.run.app", "*.onrender.com", "*.koyeb.app", "*.hf.space", "*.fly.dev", "*.up.railway.app"]


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
    if not os.environ.get("DATA_BUCKET"):
        raise SystemExit("The built data is missing and DATA_BUCKET is not set. Upload legal_store.sqlite and search_index/ to a private bucket and set DATA_BUCKET (docs/DEPLOY.md).")
    from google.cloud import storage

    n = download_bucket(storage.Client(), os.environ["DATA_BUCKET"], os.environ.get("DATA_PREFIX", ""), DATA)
    print(f"data downloaded from the bucket ({n} files)", flush=True)


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
