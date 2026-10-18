# Security and privacy design (web app and API)

Status 2026-10-18: development build, not yet deployed. No online service can honestly promise it can never be breached; the design goal is **a very small attack surface and very little to lose**.

## What exists now
| Area | Control | Where |
|---|---|---|
| Browser | Per-request nonce Content-Security-Policy: own scripts and styles only, no third-party loads, no framing, `base-uri 'none'`, `form-action 'self'`; style attributes allowed only in development (production allows none; animations use the Web Animations API, which writes no inline styles) | `web/src/proxy.ts` |
| Browser | nosniff, DENY framing, no referrer, locked-down Permissions-Policy, COOP | `web/next.config.ts`, `src/api/security.py` |
| Privacy | Fonts self-hosted at build time; no analytics, no cookies, no accounts; theme choice in this browser only | `web/src/app/layout.tsx` |
| API input | Every field typed and length-limited; unknown fields refused; control characters stripped; 16 KB body cap; error replies never repeat input | `src/api/schemas.py`, `security.py`, `app.py` |
| API abuse | Per-visitor sliding-window rate limits (agent 8/min and 40/hour; lookup 60/min; bill 30/min), cap of 300 open conversations, one answer at a time per conversation, AI call budget (`API_MAX_LLM_CALLS`) | `src/api` |
| API surface | API docs off by default, `Cache-Control: no-store`, trusted-host check, same-origin only (the web app proxies `/api`, so there is no CORS) | `app.py`, `next.config.ts` |
| Data held | Conversations in memory only, deleted after 1 hour; LLM response cache switched off for the API; feedback keeps only a rating unless the user ticks consent; no user text in logs (error type and a reference id only) | `src/api/service.py` |
| Secrets | Keys only in `.env` on the server (gitignored); never sent to the browser | `.env` |
| Supply chain | Frontend dependencies pinned to exact versions, installs run with scripts disabled, `npm audit` clean (0 known vulnerabilities, 2026-10-18), 4 runtime packages | `web/package.json`, `web/.npmrc` |
| AI misuse | The model only reads: tools are read-only (lookup, rules, exact arithmetic); user text is wrapped as data in every prompt; the duty arithmetic never goes through the model | `src/agent`, `src/tools` |

## Before it goes public (checklist)
1. **HTTPS and a domain** (owner buys it). Put a reverse proxy with automatic TLS (Caddy or nginx) in front; run Next and the API on localhost only. Set `ALLOWED_HOSTS=<domain>`, `TRUST_PROXY=1` (so rate limits see the real visitor), `API_HSTS=1`. Enable HSTS preload only after HTTPS works everywhere.
2. **Edge protection**: put the domain behind a CDN with a web application firewall and DDoS protection (for example Cloudflare's free tier), and restrict the origin server to the CDN's addresses.
3. **Shared rate limiting**: the in-memory limiter is per process. With more than one process or machine, move it (and conversations) to Redis.
4. **Logging and alerts**: access logs without bodies; alerts on 5xx spikes, 429 spikes and AI budget use. Rotate logs.
5. **AI provider**: decide the provider (DeepSeek is hosted in China; Fireworks is US-based and hosts the same open models), put the choice in the privacy page, set a hard monthly spend cap with the provider, and keep a key per environment.
6. **Legal**: privacy notice and terms reviewed by a person who knows Pakistani law; FBR's permission or terms check for reusing their documents (email sent, no reply yet).
7. **Testing**: run an external scan (OWASP ZAP baseline), check the headers at securityheaders.com, and have someone try prompt injection and oversized or malformed requests. Re-run `npm audit` and `pip-audit` on every release.
8. **Backups and recovery**: nothing user-specific is stored, so only the legal store (rebuildable from `data/raw`) and the feedback file need a backup.
9. **Process**: separate development, staging and production keys; least-privilege server user; automatic security updates; two-factor on the domain, hosting, AI and GitHub accounts.

## Known limits
* The limiter and conversation store are single-process.
* The AI provider sees what users type. Users are told not to enter personal data, but we cannot stop them.
* A page that fails open is better than one that fails closed for a money tool, but every answer shows what was not verified; this is a decision-support tool, not advice.
