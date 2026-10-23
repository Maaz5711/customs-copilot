"""One-time setup of the Hugging Face side (run from the project root, after adding the token to .env).

    HF_TOKEN=...        write token (needed to create and upload; never printed)
    HF_READ_TOKEN=...   optional second token with READ access only; it is stored as the Space secret so the running server cannot change anything.
                        If it is missing, HF_TOKEN is used for that secret and you are told to replace it.
    DEEPSEEK_API_KEY=...  already in .env; stored as a Space secret

    python deploy/hf-space/deploy.py                                   # data dataset, Space, secrets
    python deploy/hf-space/deploy.py --allowed-hosts my-site.vercel.app   # also allow the website's domain to call the API

What happens: (1) a PRIVATE dataset <you>/customs-copilot-data gets data/processed/legal_store.sqlite and data/processed/search_index (about 70 MB,
derived from FBR documents, so it stays private); (2) a public Space <you>/customs-copilot-api (Docker) gets the Dockerfile and README (the code is
cloned from the public GitHub repository at build time); (3) secrets and variables are set; (4) the script waits for the Space to run.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allowed-hosts", default="", help="comma separated website domains allowed to call the API")
    ap.add_argument("--max-llm-calls", default="1000", help="hard cap on model calls for the running server (about 5 to 9 per question)")
    ap.add_argument("--skip-data", action="store_true")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args(argv)

    load_dotenv(ROOT / ".env")
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("HF_TOKEN is not in .env yet. Create a WRITE token at huggingface.co/settings/tokens and add the line HF_TOKEN=... to .env")
        return 2
    read_token = os.environ.get("HF_READ_TOKEN", "").strip()
    api = HfApi(token=token)
    user = api.whoami()["name"]
    data_repo, space_repo = f"{user}/customs-copilot-data", f"{user}/customs-copilot-api"
    print(f"account: {user}")

    if not a.skip_data:
        for need in ("legal_store.sqlite", "search_index/tariff/emb.npy"):
            if not (ROOT / "data" / "processed" / need).exists():
                print(f"missing {need}: build the data first (README, Run it yourself)")
                return 2
        api.create_repo(data_repo, repo_type="dataset", private=True, exist_ok=True)
        if not api.repo_info(data_repo, repo_type="dataset").private:       # the data is derived from FBR documents: never public
            print("refusing to upload: the dataset is not private")
            return 3
        api.upload_folder(folder_path=str(ROOT / "data" / "processed"), repo_id=data_repo, repo_type="dataset",
                          allow_patterns=["legal_store.sqlite", "search_index/**"], commit_message="Built legal store and search indexes")
        print(f"private dataset ready: {data_repo}")

    api.create_repo(space_repo, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    for name in ("Dockerfile", "README.md"):
        api.upload_file(path_or_fileobj=str(HERE / name), path_in_repo=name, repo_id=space_repo, repo_type="space", commit_message=f"Update {name}")
    if not read_token:
        print("note: HF_READ_TOKEN is not set, so the write token is stored as the Space's read secret. Create a read-only token, set HF_READ_TOKEN, and rerun to replace it.")
    secrets = {"HF_READ_TOKEN": read_token or token, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "").strip()}
    for k, v in secrets.items():
        if v:
            api.add_space_secret(space_repo, k, v)
        else:
            print(f"warning: {k} is empty, not set")
    for k, v in {"DATA_REPO": data_repo, "API_MAX_LLM_CALLS": a.max_llm_calls, "EXTRA_ALLOWED_HOSTS": a.allowed_hosts}.items():
        if v:
            api.add_space_variable(space_repo, k, v)
    api.restart_space(space_repo)
    host = f"{user.lower()}-customs-copilot-api.hf.space"
    print(f"space: https://huggingface.co/spaces/{space_repo}   api: https://{host}")
    if a.no_wait:
        return 0
    for _ in range(90):                                                    # up to about 30 minutes: the first build downloads the models
        stage = api.get_space_runtime(space_repo).stage
        print("stage:", stage, flush=True)
        if stage == "RUNNING":
            return 0
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"):
            print("the Space failed; open its Logs tab on huggingface.co")
            return 4
        time.sleep(20)
    print("still building; check the Space page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
