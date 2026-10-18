"use client";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

// Cycles system -> light -> dark. The choice is kept in this browser only (localStorage), and applied before first paint by a tiny script in layout.tsx.
type Mode = "system" | "light" | "dark";

export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("system");
  useEffect(() => {
    try {
      const t = localStorage.getItem("cc-theme");
      if (t === "light" || t === "dark") setMode(t);
    } catch {}
  }, []);

  const next = () => {
    const m: Mode = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
    setMode(m);
    try {
      if (m === "system") {
        localStorage.removeItem("cc-theme");
        delete document.documentElement.dataset.theme;
      } else {
        localStorage.setItem("cc-theme", m);
        document.documentElement.dataset.theme = m;
      }
    } catch {}
  };

  const Icon = mode === "dark" ? Moon : Sun;
  return (
    <button type="button" onClick={next} aria-label={`Colour theme: ${mode}. Click to change.`} title={`Theme: ${mode}`}
      className="inline-flex size-11 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
      <Icon size={20} aria-hidden="true" />
      <span className="sr-only">{mode}</span>
    </button>
  );
}
