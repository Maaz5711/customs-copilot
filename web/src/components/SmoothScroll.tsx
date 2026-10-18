"use client";
import Lenis from "lenis";
import { useEffect } from "react";

// Smooth, slightly inertial scrolling on the home page (Lenis). It is skipped for people who ask for reduced motion, and touch devices keep their
// own native scrolling. Scrollable boxes inside the page carry data-lenis-prevent so they still scroll normally. Anchor links (#tool) glide.
export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ duration: 1.15, easing: (t: number) => 1 - Math.pow(1 - t, 3), smoothWheel: true, anchors: true, autoRaf: true });
    return () => lenis.destroy();
  }, []);
  return null;
}
