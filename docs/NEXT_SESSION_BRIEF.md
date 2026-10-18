# Brief for the next session: give the home page real, cinematic visuals

Written 2026-10-18 for a fresh session (the owner wants Opus 5.5). Read this, then `CLAUDE.md`, `docs/PROJECT_STATE.md` and `web/README.md`. The owner is Maaz Ahmed (5th-semester CS student, beginner): plain language, decisive recommendations, one clear next step at a time.

## What the owner asked for
A home page that **grabs attention and explains the tool as you scroll**, in the style of two example sites they recorded (`C:\Users\Maaz Ahmed\OneDrive\Desktop\WhatsApp Video 2026-10-18 at 4.25.46 PM.mp4`, 26 s, phone recording of two Instagram reels). Their feedback on the first version:

> "ours is without any real pic etc, no sea port is showing etc, so it feels AI and not interactive. It is good as per the content but it needs to be paired with better visuals."

Earlier requirements, still in force:
* On scroll, a **gate at a sea port where containers arrive** and a **checklist** showing the agent working out the import duty and the shipment getting cleared.
* People must **not mistake it for a transport or logistics website**. It is a customs duty and tax tool. Keep the story about the decision and its paperwork (code, bill, sources, "not sure", cleared), never about tracking or moving goods. No trucks-as-hero, no fleet or shipment-tracking language.
* Smooth, premium scroll motion; show the tool's purpose on the home page; later: a domain, strong security, fast, easy to use, all features.

## What the two example sites do (from frames of the video; contact sheets in `design-refs/video_contact_sheets/`, local only, not committed because they are other people's work)
* **Reel 1 (flat style, light):** pale background; flat vector truck and a reach-stacker crane with coloured containers; a dramatic **top-down container ship on dark water** with rows of coloured containers; huge short headings ("Logistics that works as hard as you do", "Reliability at every milestone"); sections change by wipes and splits.
* **Reel 2 (cinematic, "Can you believe Claude did this?"):** **photographic** scenes (a truck at sunset, a yard of containers, a desert-toned dock with numbered doors); **holographic wireframe trucks and particles laid over the photos**; glass panels; a tile grid; a **night-time Earth with glowing green route lines** for the data section; oversized words that appear line by line; a logo strip at the end.
* Common thread: **real or photographic imagery as the background of every scene, wireframe or data overlays on top, big typography, scroll-driven cross-fades.** Our version only had code-drawn wireframes on a flat background, so it looks generic.

## What exists now (all committed except the last story changes: see git status)
* **Backend**: FastAPI in `src/api` (agent ask/answer, code lookup, bill, feedback; strict validation, rate limits, security headers). Tests: `tests/test_api.py`. Run `python -m src.api`.
* **Frontend**: `web/` (Next.js 16, TypeScript, Tailwind 4, Lenis, Three.js 0.186, no GSAP). Pages: `/` tool, `/method`, `/security`. Three modes: describe a product (live agent), look up a code, calculate duty. Verified live in the browser with the real agent.
* **Scroll story v1** (`web/src/components/story/`): `Story.tsx` (pinned stage, 6 chapters, checklist, glass cards), `GateScene.ts` (Three.js: gate, abstract crate, scan beam, stacked duty layers, source sheets, candidate tags, light amber/green, all drawn in code), `chapters.ts` (copy, timing, and a REAL example run: lithium-ion power bank, PKR 500,000, total PKR 218,256.00 with sources), `KineticText`, `CountUp`, `StaticGate` (flat fallback). The server renders the plain version first (works without JavaScript); it upgrades to the pinned version when WebGL, motion and cores allow. Production build is clean in the browser console under the strict CSP.
* **Design system**: `design-system/customs-copilot/MASTER.md` (Swiss-style, navy and gold, Lexend and Source Sans 3), from the installed `ui-ux-pro-max` skill. Other installed skills worth using: `design-taste-frontend`, `high-end-visual-design`, `imagegen-frontend-web`, `image-to-code`.

## The job
Rebuild the story's **visual layer** so it feels like a premium cinematic site and clearly shows a **sea port**, while keeping the content (it is good) and the customs framing.
1. **Real imagery.** Full-bleed photographic scenes for each chapter, graded to a consistent dark, cool look: container ship arriving at dusk or night; container stacks and cranes; the inspection gate and scanner; a document or customs-office scene; sunrise at a cleared gate. Keep one flat-vector or abstract motif for the crate so the Three.js overlays still match.
2. **Overlays on the photos.** Reuse the Three.js scene as a transparent layer: holographic wireframe gate and crate, scan beam sweeping over the photo, duty layers rising, source sheets, amber and green gate light. Add a route-network or data globe for the "sources and rules" chapter if it helps the story (customs rules by date), not logistics.
3. **Scroll-driven transitions** between scenes (cross-fade, parallax, wipe or mask reveals, 0.6 to 1.2 s with eased curves), oversized staggered headings, glass cards, the live checklist. Keep Lenis. Keep the 3D layer optional and the plain fallback working.
4. **Make it more interactive**, for example: hover or tap a duty layer to see its source; a draggable scan; click a checklist step to jump to its chapter; a small "try this product" demo that fills the real tool.
5. Do not make it look like a logistics company: no fleet, tracking, "deliver", "shipping rates" language or imagery as the hero. The hero is a customs gate at a port with a code and a bill.

## Hard constraints (do not break)
* **Security**: strict nonce CSP in `web/src/proxy.ts`: no third-party scripts, styles, fonts, images or video; no inline `style` attributes in server-rendered markup (production allows none); motion with the Web Animations API or CSS; GSAP was dropped on purpose because it writes inline styles. Everything (images, video, fonts) must be **self-hosted**. Keep `npm audit` clean, exact version pins, installs with scripts disabled (`web/.npmrc`).
* **Images and rights**: do not scrape or reuse copyrighted photos or the example sites' assets. Options, in order of preference, to put to the owner (downloads and paid generation need the owner's explicit yes, with file names, source and size): (a) the owner's own photos; (b) free-licence stock (Unsplash, Pexels, Pixabay, Wikimedia Commons CC0 or CC-BY) with a recorded licence and attribution file; (c) generated imagery or video through the connected image and video generation tools (costs credits; confirm the budget first). Record every asset's source and licence in `web/public/ASSETS.md`.
* **Performance and access**: optimise images (AVIF or WebP, sized, lazy), keep the first screen fast, cap the 3D cost (it already pauses off-screen, caps pixel ratio, and skips on reduced-motion, data-saver and low-core devices), keep the plain fallback, keep text readable over photos (glass cards or gradients, contrast 4.5:1), keyboard and screen-reader access, `prefers-reduced-motion`, a "Skip to the tool" link.
* **Honesty** (project rules): every number on the page is real and sourced; no accuracy claims beyond `docs/gd_findings.md` and `/method`; the example figures come from a real run and say so.
* Do not copy code from Danial's TariffAI repo; do not copy WCO notes; secrets stay in `.env`.

## How to run and check
```bash
.venv/Scripts/python -m src.api          # API on 127.0.0.1:8000 (agent needs DEEPSEEK_API_KEY; lookup and calculator do not)
cd web && npm run dev                    # http://127.0.0.1:3000 (development; style attributes allowed here only)
cd web && npm run build && npm run start # PRODUCTION check: must show no console errors under the strict CSP
```
Preview servers are defined in `.claude/launch.json` (`api`, `web`, `web-prod`). On Windows stop the production server before rebuilding (file lock). The browser pane renders slowly and animations lag; wait several seconds before screenshots, and test narrow (about 580 px) and wide layouts. Tests: `.venv/Scripts/python -m pytest -q tests` (493 pass); front end: `npx tsc --noEmit`, `npm run build`, `npm run audit` in `web/`.

## Open decisions for the owner (ask one at a time)
1. Image source and budget (own photos, free stock, or generated).
2. Whether to also offer a separate static "light" home for low-power phones (the plain fallback exists).
3. Domain, hosting and the pre-launch checklist in `docs/security.md` (the owner buys the domain; no reply from FBR yet).

## Other pending work (not for this session unless asked)
Spot-check sheets for the Fifth Schedule and China FTA; the 84 unreadable rows of the China FTA table; automotive and oil-and-gas SRO files (downloaded to `data/raw/auto_ep_sros/`, not yet read); decision checklists per tariff heading; precedent memory from user-confirmed answers; DeepSeek and Fireworks credit are low.
