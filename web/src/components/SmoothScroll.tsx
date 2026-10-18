"use client";
import Lenis from "lenis";
import { useEffect } from "react";

// Smooth, slightly inertial scrolling on the home page (Lenis). It is skipped for people who ask for reduced motion, and touch devices keep their
// own native scrolling. Scrollable boxes inside the page carry data-lenis-prevent so they still scroll normally. Anchor links (#tool) glide.
let active: Lenis | null = null;

/** Glide to a page position (smoothly through Lenis when it runs, otherwise the browser's own scrolling). */
export function glideTo(y: number) {
  if (active) active.scrollTo(y, { duration: 1.4 });
  else window.scrollTo({ top: y, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ duration: 1.15, easing: (t: number) => 1 - Math.pow(1 - t, 3), smoothWheel: true, anchors: true, autoRaf: true });
    active = lenis;
    return () => { active = null; lenis.destroy(); };
  }, []);
  return null;
}
