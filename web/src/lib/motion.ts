"use client";
import { useEffect, useRef } from "react";

// Entrance motion with the browser's own Web Animations API. It needs no library, it does not write inline style attributes (so the strict
// Content-Security-Policy stays strict), it is skipped for people who ask their system for reduced motion, and the content is fully
// visible without it. `key` re-runs the animation when new content replaces the old.
export function useReveal<T extends HTMLElement>(key: unknown = null, selector = "[data-reveal]") {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof el.animate !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const running = [...el.querySelectorAll<HTMLElement>(selector)].map((node, i) =>
      node.animate(
        [{ opacity: 0, transform: "translateY(14px)" }, { opacity: 1, transform: "none" }],
        { duration: 420, delay: Math.min(i, 12) * 60, easing: "cubic-bezier(0.22, 0.61, 0.36, 1)", fill: "backwards" },
      ),
    );
    return () => running.forEach((a) => a.cancel());
  }, [key, selector]);
  return ref;
}
