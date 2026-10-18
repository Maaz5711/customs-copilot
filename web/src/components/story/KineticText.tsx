"use client";
import { useEffect, useRef } from "react";

// A heading whose words rise in one after another (0.8 s each, 55 ms apart) when it becomes active. Screen readers get the plain heading;
// the animated copy is hidden from them. Without motion (reduced-motion setting) the heading simply appears.
export function KineticText({ text, level = 2, active, className }: { text: string; level?: 1 | 2; active: boolean; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !active || typeof el.animate !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const anims = [...el.querySelectorAll<HTMLElement>("[data-w]")].map((s, i) =>
      s.animate([{ opacity: 0, transform: "translateY(0.55em)" }, { opacity: 1, transform: "none" }], { duration: 800, delay: 120 + i * 55, easing: "cubic-bezier(0.22, 0.61, 0.36, 1)", fill: "backwards" }),
    );
    return () => anims.forEach((a) => a.cancel());
  }, [active, text]);

  const inner = (
    <>
      <span className="sr-only">{text}</span>
      <span ref={ref} aria-hidden="true">
        {text.split(" ").map((w, i) => (
          <span key={i}>
            <span data-w className="inline-block">{w}</span>{" "}
          </span>
        ))}
      </span>
    </>
  );
  return level === 1 ? <h1 className={className}>{inner}</h1> : <h2 className={className}>{inner}</h2>;
}
