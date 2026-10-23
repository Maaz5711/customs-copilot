"""Start script for the Hugging Face Space: fetch the private data once, then run the API on port 7860.

Secrets and variables (Space settings):  HF_READ_TOKEN (read-only token), DATA_REPO (for example user/customs-copilot-data),
DEEPSEEK_API_KEY, API_MAX_LLM_CALLS (hard cap on model calls for this process), EXTRA_ALLOWED_HOSTS (the website's domain, comma separated).
"""
from __future__ import annotations

import os
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"


def fetch_data() -> None:
    if (DATA / "legal_store.sqlite").exists() and (DATA / "search_index" / "tariff" / "emb.npy").exists():
        return
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=os.environ["DATA_REPO"], repo_type="dataset", token=os.environ["HF_READ_TOKEN"], local_dir=str(DATA))
    print("data downloaded", flush=True)


def main() -> None:
    fetch_data()
    hosts = [os.environ.get("SPACE_HOST", ""), *os.environ.get("EXTRA_ALLOWED_HOSTS", "").split(","), "localhost", "127.0.0.1"]
    os.environ["ALLOWED_HOSTS"] = ",".join(h.strip() for h in hosts if h.strip())
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    runpy.run_module("src.api", run_name="__main__")


if __name__ == "__main__":
    main()
