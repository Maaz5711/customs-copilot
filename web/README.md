# Customs Copilot web app

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. The browser only talks to this app; `/api/*` is forwarded to the Python API (`src/api`), so there is no cross-origin traffic.

## Run it (development)
```bash
# terminal 1, project root: the API (needs DEEPSEEK_API_KEY in .env for the agent; lookup and calculator need no key)
.venv/Scripts/python -m src.api            # http://127.0.0.1:8000

# terminal 2: the web app
cd web && npm install && npm run dev       # http://127.0.0.1:3000
```
Production check: `npm run build && npm run start`. Type check: `npm run typecheck`. Dependency audit: `npm run audit`.

## What is where
* `src/app/` pages: `/` (the tool), `/method` (how it works and the measured accuracy), `/security` (privacy and security).
* `src/components/` `Tool` (three tabs + date), `AgentPanel` + `Questions` + `ResultView` (agent), `LookupPanel` (code lookup), `BillPanel` (calculator), `BillTable`, `Feedback`.
* `src/proxy.ts` the Content-Security-Policy with a nonce per request. `src/lib/api.ts` the typed API client. `src/lib/motion.ts` entrance animation (Web Animations API, respects reduced motion).
* Design system: `../design-system/customs-copilot/MASTER.md` (Swiss-style minimal, navy with a gold accent, Lexend and Source Sans 3).

## Rules for changes
* No inline `style` attributes in server-rendered markup, no third-party scripts, fonts or images (the policy blocks them). Use Tailwind classes and tokens in `globals.css`.
* Pin new dependencies to exact versions and run `npm audit` before committing.
* Never log or store what users type.
