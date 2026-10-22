# Deploying the public beta

The site has two parts and both must be reachable, or the tool shows errors:

| Part | What it is | Where it can run |
|---|---|---|
| **Website** | Next.js app in `web/` | Vercel (free hobby plan is enough) |
| **API** | FastAPI + agent in `src/`, needs the built legal store (`data/processed/legal_store.sqlite`, about 100 MB), the search indexes (`data/processed/search_index/`, about 300 MB), two small local ONNX models (downloaded on first start) and about 2 GB of memory | a small server or container: a VPS, Render, Fly.io, Railway or a Hugging Face Space (Docker). **Not Vercel serverless** (memory, size and 60-second limits are too tight for the agent) |

The website forwards every `/api/*` request to the API (`web/next.config.ts`, variable `API_ORIGIN`), so the browser only ever talks to one origin.

## Steps
1. **Build the data once, locally** from the official FBR PDFs (README, quick start): `python -m src.store.build` and `python -m src.search.build`. The data is derived from FBR publications and is **not** committed to the public repository; copy the two outputs to the API host privately.
2. **API host**: build the `Dockerfile` (or run `python -m src.api` behind HTTPS), place the data under `data/processed/`, and set:
   * `ALLOWED_HOSTS=<api hostname>`, `TRUST_PROXY=1`, `API_HSTS=1` (already in the Dockerfile)
   * `LLM_PROVIDER=deepseek` and `DEEPSEEK_API_KEY=...` (or `gemini`, `fireworks`, `openrouter`)
   * `API_MAX_LLM_CALLS=<hard cap per process>` and a **monthly spend cap in the provider's dashboard**
3. **Website on Vercel**: import the GitHub repository, set **Root Directory** to `web`, add the environment variable `API_ORIGIN=https://<api hostname>`, deploy.
4. Open the site, ask one question, and check that the "Thinking" steps appear and a bill comes back.
5. Walk through the checklist in `docs/security.md` before inviting people (privacy notice, spend cap, edge protection).

## What not to skip
* **Privacy**: what users type is sent to the AI provider (DeepSeek's servers are in China, Fireworks' in the US). The site already tells users not to enter personal data; say which provider is used on the privacy page.
* **Cost**: each question uses about 5 to 9 model calls (roughly 0.1 to 0.5 US cents on DeepSeek flash). The per-IP limits and `API_MAX_LLM_CALLS` stop a runaway bill, but set the provider's own cap too.
* **FBR documents**: serving answers computed from FBR publications is the tool's purpose; do not publish the data tables themselves until FBR replies to the permission email (`docs/case_collection/email_draft.md`).
