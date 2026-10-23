"""Start script for any container host (Google Cloud Run, Render, Koyeb, Hugging Face Space, a VM): fetch the private data once, then run the API.

The built data (legal store and search indexes, derived from FBR documents) is not in git or in the image. It is downloaded at start-up from a
PRIVATE Hugging Face dataset with a read-only token. Environment variables (set them in the host's dashboard as secrets):
    HF_READ_TOKEN      read-only Hugging Face token
    DATA_REPO          private dataset, for example Maaz369/customs-copilot-data
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


def fetch_data() -> None:
    if (DATA / "legal_store.sqlite").exists() and (DATA / "search_index" / "tariff" / "emb.npy").exists():
        return
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=os.environ["DATA_REPO"], repo_type="dataset", token=os.environ["HF_READ_TOKEN"], local_dir=str(DATA))
    print("data downloaded", flush=True)


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
