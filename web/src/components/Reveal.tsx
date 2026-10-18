"use client";
import { useReveal } from "@/lib/motion";

// Wraps server-rendered content and fades its [data-reveal] children in on load. Content is visible without JavaScript.
export function Reveal({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useReveal<HTMLDivElement>("load");
  return <div ref={ref} className={className}>{children}</div>;
}
