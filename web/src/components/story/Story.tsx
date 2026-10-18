"use client";
import { ArrowDown, Check } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { GateScene as GateSceneType } from "./GateScene";
import { CHAPTERS, EXAMPLE, chapterAt, clamp01, fmtPKR } from "./chapters";
import { CountUp } from "./CountUp";
import { KineticText } from "./KineticText";
import { StaticGate } from "./StaticGate";

// The home page story. The server sends the plain version (all chapters stacked, flat drawing), which also works without JavaScript. On a capable
// device the page upgrades to the pinned version: one sticky stage, a 3D gate scene driven by scroll, and the chapters crossfading over it.
// Skipped for: reduced-motion setting, data-saver, very low-core devices, no WebGL, or a lost WebGL context.

type SceneCtor = { new (c: HTMLCanvasElement): GateSceneType; supported(): boolean };

export function Story() {
  const [mode, setMode] = useState<"static" | "pinned">("static");
  const [idx, setIdx] = useState(0);
  const trackRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctorRef = useRef<SceneCtor | null>(null);

  // 1. Decide whether the 3D version is worth it, and only then download it.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const saver = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
    const cores = navigator.hardwareConcurrency ?? 4;
    if (reduced || saver || cores <= 2) return;
    let dead = false;
    import("./GateScene").then(({ GateScene }) => {
      if (dead || !GateScene.supported()) return;
      ctorRef.current = GateScene as unknown as SceneCtor;
      setMode("pinned");
    });
    return () => { dead = true; };
  }, []);

  // 2. Run the scene while the story is on screen.
  useEffect(() => {
    if (mode !== "pinned") return;
    const track = trackRef.current, stage = stageRef.current, canvas = canvasRef.current, Ctor = ctorRef.current;
    if (!track || !stage || !canvas || !Ctor) return;
    const scene = new Ctor(canvas);
    scene.onLost = () => setMode("static");

    const size = () => scene.setSize(stage.clientWidth, stage.clientHeight);
    const ro = new ResizeObserver(size);
    ro.observe(stage);
    size();

    const update = () => {
      const r = track.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      const p = total > 0 ? clamp01(-r.top / total) : 0;
      scene.setProgress(p);
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

  const pinned = mode === "pinned";
  const on = (i: number) => !pinned || idx === i;
  const last = CHAPTERS.length - 1;

  return (
    <section ref={trackRef} id="story" data-mode={mode} aria-label="How an answer is made" className="story">
      <div ref={stageRef} className="story-stage">
        <canvas ref={canvasRef} className="story-canvas" aria-hidden="true" />
        <div className="story-flat mx-auto max-w-5xl px-4 pt-8 sm:px-6"><StaticGate className="mx-auto w-full max-w-xl" /></div>

        <a href="#tool" className="story-skip glass">Skip to the tool</a>

        {pinned && (
          <>
            <div className="story-bar md:hidden" aria-hidden="true">
              {CHAPTERS.map((c, i) => <span key={c.id} className={i <= idx ? "is-on" : ""} />)}
            </div>
            <aside className="story-check glass hidden md:block" aria-label="Progress">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-2">Clearance checklist</p>
              <ol className="grid gap-2">
                {CHAPTERS.map((c, i) => {
                  const done = i < idx || (i === idx && idx === last);
                  const now = i === idx && !done;
                  return (
                    <li key={c.id} className={`story-step ${done ? "is-done" : now ? "is-now" : ""}`}>
                      <span className="story-tick" aria-hidden="true">{done ? <Check size={13} strokeWidth={3} /> : null}</span>
                      <span>{c.step}</span>
                    </li>
                  );
                })}
              </ol>
            </aside>
          </>
        )}

        <div className="story-panels">
          {CHAPTERS.map((c, i) => {
            const active = on(i);
            return (
              <article key={c.id} data-active={active} data-card={["code", "bill", "sources", "unsure"].includes(c.id)} aria-hidden={pinned && !active ? true : undefined} inert={pinned && !active} className="story-panel glass">
                <p className="text-sm font-semibold uppercase tracking-wider text-gold">{c.kicker}</p>
                <KineticText text={c.title} level={i === 0 ? 1 : 2} active={active && pinned} className="story-title mt-2 font-display text-3xl font-semibold leading-[1.1] sm:text-4xl" />
                <p className="story-body mt-3 text-[17px] text-ink-2">{c.body}</p>

                {c.id === "arrive" && (
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <a href="#tool" className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">Try the tool</a>
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
                            {c.id === "bill" && <td className="num py-2 text-right font-semibold">{c.id === "bill" ? <CountUp to={l.amount} active={active && pinned} delay={k * 140} /> : null}</td>}
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
                    <a href="#tool" className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">Open the tool</a>
                    <Link href="/method#accuracy" className="inline-flex min-h-11 items-center rounded-lg border border-line px-5 py-2 text-[15px] font-semibold transition-colors hover:bg-surface-2">See how accurate it is</Link>
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
