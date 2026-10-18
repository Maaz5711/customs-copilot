"use client";
import { ArrowDown, Check, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { glideTo } from "../SmoothScroll";
import type { PortScene as PortSceneType } from "./PortScene";
import { CHAPTERS, EXAMPLE, PINS, TRY_TEXT, chapterAt, clamp01, fmtPKR } from "./chapters";
import { CountUp } from "./CountUp";
import { KineticText } from "./KineticText";
import { PortSketch } from "./PortSketch";

// The home page story. The server sends the plain version (a flat sketch of the port and all chapters stacked as cards), which also works without
// JavaScript. On a capable device the page upgrades to the pinned version: one sticky stage with a hand-drafted 3D port that plays as you scroll
// (ship docks, crane lifts the container, a clearing agent checks it, the bill stacks up, the truck leaves through the green gate), source pins you can
// open, a clearance log that jumps to each step, and the chapters crossfading on top. White paper in light theme, blueprint in dark theme.
// The 3D version is skipped for: reduced-motion setting, data-saver, very low-core devices, no WebGL, or a lost WebGL context.

type SceneCtor = { new (c: HTMLCanvasElement): PortSceneType; supported(): boolean };
type GateLike = { snap(): void };

const pad = (n: number) => String(n).padStart(3, "0");

export function Story() {
  const [mode, setMode] = useState<"static" | "pinned">("static");
  const [idx, setIdx] = useState(0);
  const [openPin, setOpenPin] = useState<string | null>(null);
  const trackRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const readoutRef = useRef<HTMLSpanElement>(null);
  const ctorRef = useRef<SceneCtor | null>(null);

  // 1. Decide whether the pinned version is worth it, and only then download the 3D code.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const saver = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
    const cores = navigator.hardwareConcurrency ?? 4;
    if (reduced || saver || cores <= 2) return;
    let dead = false;
    import("./PortScene").then(({ PortScene }) => {
      if (dead || !PortScene.supported()) return;
      ctorRef.current = PortScene as unknown as SceneCtor;
      setMode("pinned");
    });
    return () => { dead = true; };
  }, []);

  // 2. Run the scene and the readout while the story is on screen.
  useEffect(() => {
    if (mode !== "pinned") return;
    const track = trackRef.current, stage = stageRef.current, canvas = canvasRef.current, Ctor = ctorRef.current;
    if (!track || !stage || !canvas || !Ctor) return;
    const scene = new Ctor(canvas);
    scene.onLost = () => setMode("static");
    if (process.env.NODE_ENV === "development") (window as Window & { __story?: GateLike }).__story = scene;

    const size = () => scene.setSize(stage.clientWidth, stage.clientHeight);
    const ro = new ResizeObserver(size);
    ro.observe(stage);
    size();

    const update = () => {
      const r = track.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      const p = total > 0 ? clamp01(-r.top / total) : 0;
      scene.setProgress(p);
      if (readoutRef.current) readoutRef.current.textContent = p.toFixed(3);
      const c = CHAPTERS.indexOf(chapterAt(p));
      setIdx((prev) => (prev === c ? prev : c));
    };
    let queued = false;
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; update(); });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();

    const io = new IntersectionObserver(([e]) => scene.setVisible(!!e?.isIntersecting), { rootMargin: "120px" });
    io.observe(track);

    // The drawing follows the site theme: white paper in light, blueprint in dark.
    const retheme = () => scene.refreshTheme();
    const mo = new MutationObserver(retheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", retheme);

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      ro.disconnect(); io.disconnect(); mo.disconnect();
      mq.removeEventListener("change", retheme);
      scene.dispose();
    };
  }, [mode]);

  // A newly shown chapter starts with its pins closed.
  useEffect(() => setOpenPin(null), [idx]);

  /** Scroll so that chapter i is on screen (the checklist steps are buttons that jump). */
  const jump = (i: number) => {
    const track = trackRef.current;
    if (!track) return;
    const top = track.getBoundingClientRect().top + window.scrollY;
    const total = track.offsetHeight - window.innerHeight;
    const c = CHAPTERS[i]!;
    glideTo(top + total * Math.min(c.to - 0.01, c.from + 0.035) + (i === 0 ? 0 : 1));
  };

  /** Put the example into the tool and go there. */
  const tryIt = () => {
    window.dispatchEvent(new CustomEvent("cc:try", { detail: TRY_TEXT }));
    const tool = document.getElementById("ask");
    if (tool) glideTo(tool.getBoundingClientRect().top + window.scrollY - 8);
  };

  const pinned = mode === "pinned";
  const on = (i: number) => !pinned || idx === i;
  const last = CHAPTERS.length - 1;
  const cur = CHAPTERS[idx]!;

  const TryButton = ({ primary }: { primary?: boolean }) => (
    <button type="button" onClick={tryIt}
      className={primary
        ? "inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90"
        : "inline-flex min-h-11 items-center gap-2 rounded-lg border border-line px-5 py-2 text-[15px] font-semibold transition-colors hover:bg-surface-2"}>
      <Sparkles size={16} aria-hidden="true" /> Try this product
    </button>
  );

  return (
    <section ref={trackRef} id="story" data-mode={mode} aria-label="How an answer is made" className="story">
      <div ref={stageRef} className="story-stage">
        <canvas ref={canvasRef} className="story-canvas" aria-hidden="true" />
        <div className="story-flat mx-auto max-w-5xl px-4 pt-14 sm:px-6"><PortSketch className="mx-auto w-full max-w-3xl" /></div>

        {/* drawing-sheet frame: corner marks and readouts, like a technical drawing */}
        {pinned && (
          <div className="story-hud" aria-hidden="true">
            <span className="hud-corner hud-tl" /><span className="hud-corner hud-tr" /><span className="hud-corner hud-bl" /><span className="hud-corner hud-br" />
            <p className="hud-meta hud-meta-tl">CUSTOMS COPILOT · PK<br />FILE {EXAMPLE.code} · RULES AS OF {EXAMPLE.asOf.toUpperCase()}</p>
            <p className="hud-meta hud-meta-br">SHEET {String(idx + 1).padStart(2, "0")} / {String(CHAPTERS.length).padStart(2, "0")} · P=<span ref={readoutRef}>0.000</span></p>
          </div>
        )}

        <a href="#tool" className="story-skip glass">Skip to the tool</a>

        {pinned && (
          <>
            <div className="story-bar md:hidden" aria-hidden="true">
              {CHAPTERS.map((c, i) => <span key={c.id} className={i <= idx ? "is-on" : ""} />)}
            </div>
            <nav className="story-check glass hidden md:block" aria-label="Clearance checklist: jump to a step">
              <p className="hud-label mb-2">Clearance log</p>
              <ol className="grid gap-1">
                {CHAPTERS.map((c, i) => {
                  const done = i < idx || (i === idx && idx === last);
                  const now = i === idx && !done;
                  return (
                    <li key={c.id}>
                      <button type="button" onClick={() => jump(i)} aria-current={i === idx ? "step" : undefined} className={`story-step ${done ? "is-done" : now ? "is-now" : ""}`}>
                        <span className="story-tick" aria-hidden="true">{done ? <Check size={12} strokeWidth={3} /> : null}</span>
                        <span className="story-no">{pad(i + 1)}</span>
                        <span>{c.step}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            {/* source pins for the chapter on screen: hover, focus or tap to read the source */}
            <ul className="story-pins" aria-label={`Sources for: ${cur.step}`} key={cur.id}>
              {(PINS[cur.id] ?? []).map((pin, k) => {
                const id = `${cur.id}-${k}`;
                const open = openPin === id;
                return (
                  <li key={id} className={`pin pin-${pin.slot} pin-d${k}`}>
                    <button type="button" className="pin-btn" aria-expanded={open} aria-controls={`pin-${id}`} onClick={() => setOpenPin(open ? null : id)}>
                      <span className="pin-dot" aria-hidden="true" />
                      <span className="pin-tag">{pin.tag}</span>
                    </button>
                    <div id={`pin-${id}`} className="pin-detail glass" data-open={open}>
                      <p className="text-[14px] font-semibold text-ink">{pin.text}</p>
                      <p className="hud-label mt-1 normal-case">Source · {pin.src}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        <div className="story-panels">
          {CHAPTERS.map((c, i) => {
            const active = on(i);
            return (
              <article key={c.id} data-active={active} data-card={["code", "bill", "sources", "unsure"].includes(c.id)} aria-hidden={pinned && !active ? true : undefined} inert={pinned && !active} className="story-panel glass">
                <p className="hud-label text-gold">{pad(i + 1)} · {c.kicker}</p>
                <KineticText text={c.title} level={2} active={active && pinned} className="story-title mt-2 font-display font-semibold" />
                <p className="story-body mt-3 text-[17px] text-ink-2">{c.body}</p>

                {c.id === "arrive" && (
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <a href="#ask" className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">Try the tool</a>
                    <Link href="/method" className="inline-flex min-h-11 items-center rounded-lg border border-line px-5 py-2 text-[15px] font-semibold transition-colors hover:bg-surface-2">How it works</Link>
                  </div>
                )}

                {c.id === "code" && (
                  <div className="story-card">
                    <p className="text-sm text-ink-2">Goods</p>
                    <p className="font-semibold">{EXAMPLE.product}</p>
                    <ul className="my-3 grid gap-1 text-[15px]">
                      {EXAMPLE.questions.map(([q, a]) => <li key={q} className="flex justify-between gap-3"><span className="text-ink-2">{q}</span><span className="font-semibold">{a}</span></li>)}
                    </ul>
                    <p className="text-sm text-ink-2">Tariff line</p>
                    <p className="num font-display text-2xl font-semibold">{EXAMPLE.code} <span className="ml-2 align-middle rounded-full bg-gold-soft px-2.5 py-0.5 font-sans text-xs font-semibold text-gold">92% confident</span></p>
                    <p className="text-[15px] text-ink-2">{EXAMPLE.codeName}</p>
                    <div className="mt-3"><TryButton /></div>
                  </div>
                )}

                {(c.id === "bill" || c.id === "sources") && (
                  <div className="story-card">
                    <table className="w-full text-left text-[15px]">
                      <caption className="sr-only">Example bill for {EXAMPLE.product}</caption>
                      <tbody>
                        {EXAMPLE.lines.map((l, k) => (
                          <tr key={l.tax} className="story-row border-b border-line last:border-0" data-k={k}>
                            <th scope="row" className="py-2 pr-3 font-normal">
                              {c.id === "bill" ? <>{l.label} <span className="text-xs text-ink-2">{l.rate}</span></> : <><span className="num font-semibold">{l.tax}</span> <span className="text-xs text-ink-2">{l.source}</span></>}
                            </th>
                            {c.id === "bill" && <td className="num py-2 text-right font-semibold"><CountUp to={l.amount} active={active && pinned} delay={k * 140} /></td>}
                          </tr>
                        ))}
                        {c.id === "bill" && (
                          <tr className="border-t-2 border-ink">
                            <th scope="row" className="pt-3 text-base">Total payable</th>
                            <td className="num pt-3 text-right font-display text-xl font-semibold">PKR <CountUp to={EXAMPLE.total} active={active && pinned} delay={900} /></td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                    {c.id === "sources" && (
                      <ul className="mt-3 grid gap-1 border-t border-line pt-3 text-sm text-ink-2">
                        <li className="font-semibold text-ink">Not verified</li>
                        {EXAMPLE.unverified.map((u) => <li key={u}>· {u}</li>)}
                      </ul>
                    )}
                    <p className="mt-3 text-xs text-ink-2">Real run of the tool: assessed value PKR {fmtPKR(EXAMPLE.value).replace(".00", "")}, {EXAMPLE.who}, rules as of {EXAMPLE.asOf}.</p>
                  </div>
                )}

                {c.id === "unsure" && (
                  <div className="story-card">
                    <p className="mb-2 text-sm font-semibold text-warn">Top candidates (illustration)</p>
                    <ul className="flex flex-wrap gap-2">
                      {EXAMPLE.candidates.map((x) => <li key={x} className="num rounded-lg border border-warn/50 bg-warn-soft px-3 py-1.5 text-[15px] font-semibold text-warn">{x}</li>)}
                    </ul>
                  </div>
                )}

                {c.id === "clear" && (
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <TryButton primary />
                    <a href="#ask" className="inline-flex min-h-11 items-center rounded-lg border border-line px-5 py-2 text-[15px] font-semibold transition-colors hover:bg-surface-2">Open the tools</a>
                    <Link href="/method#accuracy" className="inline-flex min-h-11 items-center px-2 py-2 text-[15px] font-semibold text-ink-2 underline-offset-4 hover:text-ink hover:underline">How accurate is it?</Link>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        {pinned && idx === 0 && (
          <div className="story-cue" aria-hidden="true"><ArrowDown size={18} /> Scroll</div>
        )}
      </div>
    </section>
  );
}
