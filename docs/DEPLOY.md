# Deploying the public beta (free tiers)

Two parts, both must be reachable or the tool shows errors:

| Part | What it is | Where it runs |
|---|---|---|
| **Website** | Next.js app in `web/`: the pages, the 3D story, the forms | **Vercel** (free hobby plan) |
| **API** | FastAPI + the agent in `src/`: search, classification, exact duty maths. Needs about 0.9 GB of memory and the built data (legal store 27 MB + search indexes 42 MB, 31 MB zipped) | a container host: **Azure Container Apps** (Azure for Students, no card), Google Cloud Run (card with a US$50 hold), Koyeb/Render if shrunk to 512 MB, or a VM |

The website forwards every `/api/*` request to the API (`web/next.config.ts`, variable `API_ORIGIN`), so the browser only talks to one address. The API calls a language model (DeepSeek by default).

**The container image holds code only.** GitHub Actions builds it from this public repository (`.github/workflows/docker.yml`) and publishes `ghcr.io/maaz5711/customs-copilot-api:latest`. The built data is derived from FBR publications, so it is **not** in git or in the image: `deploy/start.py` downloads it when the container starts, from a **private link you control** (`DATA_ZIP_URL`).

## Steps (Azure for Students)
1. **Build and pack the data once, locally** from the official FBR PDFs (README, Run it yourself): `python -m src.store.build`, `python -m src.search.build`, then `python deploy/pack_data.py`. It writes `deploy/out/customs-copilot-data.zip` (never committed) and prints its SHA-256.
2. **Azure for Students**: sign up at https://azure.microsoft.com/en-us/free/students with a university email (no card). Create a **Storage account** (Standard, LRS) with a **private** container, upload the zip, then open the blob and **Generate SAS**: permission *Read* only, HTTPS only, expiry about a year. Copy the **Blob SAS URL**: it works like a password.
3. **Image**: in the GitHub repository, *Actions* must show a green "Build API image" run. In *Packages*, open `customs-copilot-api` → Package settings → change visibility to **Public** (the image contains no data).
4. **API**: open Azure **Cloud Shell** (Bash, the `>_` icon) and run `deploy/azure/deploy.sh` (the command is at the top of the script). It asks for a region, the SAS URL, the SHA-256 and your DeepSeek key (hidden input), creates a Container App with 1 CPU, 2 GiB, **at most one instance**, and prints the API address.
5. **Vercel**: create a project from this repository with **Root Directory** `web` and the environment variable `API_ORIGIN=https://<the API address>`.
6. Ask one question on the live site and check that the "Thinking" steps appear and a bill comes back, then walk through `docs/security.md`.

## Other hosts
* **Google Cloud Run**: create a service from the public image (or from the repository with the root Dockerfile), request-based billing, 2 GiB, max instances 1; variables `DATA_ZIP_URL` (a signed URL) or `DATA_BUCKET` (a private bucket read by the service account), `DEEPSEEK_API_KEY`, `API_MAX_LLM_CALLS=1000`. Google verifies cards with a US$50 temporary hold.
* **Anything with 1 GB or more of memory** can run the image with the same variables. 512 MB hosts are too small unless the search models are shrunk.

## What not to skip
* **Privacy**: what users type is sent to the language-model provider (DeepSeek's servers are in China). The site tells users not to enter personal data; say which provider is used on the privacy page.
* **Cost**: each question uses about 5 to 9 model calls (roughly 0.1 to 0.5 US cents on DeepSeek flash). Per-IP limits and `API_MAX_LLM_CALLS` stop a runaway bill; DeepSeek is prepaid, so it stops at zero. Watch the Azure credit.
* **FBR documents**: serving answers computed from FBR publications is the tool's purpose, but do not publish the data tables themselves until FBR replies to the permission email (`docs/case_collection/email_draft.md`). Keep the SAS link private and let it expire.
* A cold start (first question after the service scaled to zero) takes about a minute while the container starts and downloads the data; a conversation left idle for several minutes may expire.
