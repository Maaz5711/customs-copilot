"use client";
import { useEffect, useRef } from "react";
import { fmtPKR } from "./chapters";

// Counts up to `to` (1.2 s, ease-out) each time `active` becomes true. It writes text directly, so scrolling never re-renders React.
// The server and the no-motion case show the final figure, so the number is always readable.
export function CountUp({ to, active, delay = 0, className }: { to: number; active: boolean; delay?: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!active || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmtPKR(to); return; }
    let raf = 0;
    const start = performance.now() + delay;
    el.textContent = fmtPKR(0);
    const step = (now: number) => {
      const k = Math.min(1, Math.max(0, (now - start) / 1200));
      el.textContent = fmtPKR(to * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step); else el.textContent = fmtPKR(to);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [active, to, delay]);
  return <span ref={ref} className={className}>{fmtPKR(to)}</span>;
}
