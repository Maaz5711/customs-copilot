# Deploying the public beta (free tiers)

Two parts, both must be reachable or the tool shows errors:

| Part | What it is | Where it runs |
|---|---|---|
| **Website** | Next.js app in `web/`: the pages, the 3D story, the forms | **Vercel** (free hobby plan) |
| **API** | FastAPI + the agent in `src/`: search, classification, exact duty maths. Needs about 0.9 GB of memory and the built data (legal store 27 MB + search indexes 42 MB) | **Google Cloud Run** (free within monthly quotas, scales to zero) |

The website forwards every `/api/*` request to the API (`web/next.config.ts`, variable `API_ORIGIN`), so the browser only talks to one address. The API calls a language model (DeepSeek by default).

The built data is derived from FBR publications, so it is **not** in git or in the container image. It lives in a **private Google Cloud Storage bucket in your own account**; `deploy/start.py` copies it into the container when the service starts.

## Steps
1. **Build the data once, locally** from the official FBR PDFs (README, Run it yourself): `python -m src.store.build` and `python -m src.search.build`.
2. **Bucket**: Cloud Storage, create a bucket (any unique name, region `us-central1`, Standard, public access prevented). Upload `data/processed/legal_store.sqlite` and the folder `data/processed/search_index` to the bucket root.
3. **Cloud Run**: create a service from this repository (Dockerfile at the root). Request-based billing, memory 2 GiB, 1 CPU, timeout 300 s, minimum instances 0, **maximum instances 1** (conversations live in memory, and it caps spending). Environment variables: `DATA_BUCKET=<bucket name>`, `DEEPSEEK_API_KEY`, `API_MAX_LLM_CALLS=1000`. Give the service's service account the role **Storage Object Viewer** on the bucket.
4. **Vercel**: create a project from this repository with **Root Directory** `web` and the environment variable `API_ORIGIN=https://<your Cloud Run URL>`.
5. Ask one question on the live site and check that the "Thinking" steps appear and a bill comes back, then walk through `docs/security.md`.

## What not to skip
* **Privacy**: what users type is sent to the language-model provider (DeepSeek's servers are in China). The site tells users not to enter personal data; say which provider is used on the privacy page.
* **Cost**: each question uses about 5 to 9 model calls (roughly 0.1 to 0.5 US cents on DeepSeek flash). Per-IP limits and `API_MAX_LLM_CALLS` stop a runaway bill; set a monthly cap with the provider too and keep a budget alert on Google Cloud.
* **FBR documents**: serving answers computed from FBR publications is the tool's purpose, but do not publish the data tables themselves until FBR replies to the permission email (`docs/case_collection/email_draft.md`).
* A cold start (first question after the service slept) takes about a minute while the container starts and copies the data.
