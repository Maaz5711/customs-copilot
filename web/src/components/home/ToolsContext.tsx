"use client";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Meta } from "@/lib/types";
import { glideTo } from "../SmoothScroll";

// Shared state for the home page tools: one "rules as of" date for every tool, the text handed to the agent (from the search box chips,
// the common-imports cards or the story's "Try this product"), and the code handed to the calculator.

export type Seed = { text: string; n: number; run?: boolean };
type Ctx = {
  date: string; setDate: (d: string) => void; meta: Meta | null;
  seed: Seed; ask: (text: string) => void;
  codeSeed: { value: string; n: number }; calc: (code: string) => void;
  go: (id: string) => void;
};

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Glide to a section, leaving room for the sticky header. */
export const go = (id: string) => {
  const el = document.getElementById(id);
  if (el) glideTo(el.getBoundingClientRect().top + window.scrollY - 84);
};

const ToolsCtx = createContext<Ctx | null>(null);

export function ToolsProvider({ children }: { children: ReactNode }) {
  const [date, setDate] = useState(localToday());
  const [meta, setMeta] = useState<Meta | null>(null);
  const [seed, setSeed] = useState<Seed>({ text: "", n: 0 });
  const [codeSeed, setCodeSeed] = useState({ value: "", n: 0 });

  useEffect(() => {
    api.meta().then((m) => { setMeta(m); setDate(m.today); }).catch(() => {});
  }, []);

  const ask = (text: string) => { setSeed((s) => ({ text, n: s.n + 1, run: true })); go("ask"); };
  const calc = (code: string) => { setCodeSeed((s) => ({ value: code, n: s.n + 1 })); go("calculate"); };

  // "Try this product" in the story asks the agent about its example.
  useEffect(() => {
    const onTry = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text === "string" && text) setSeed((s) => ({ text, n: s.n + 1, run: true }));
    };
    window.addEventListener("cc:try", onTry);
    return () => window.removeEventListener("cc:try", onTry);
  }, []);

  return <ToolsCtx.Provider value={{ date, setDate, meta, seed, ask, codeSeed, calc, go }}>{children}</ToolsCtx.Provider>;
}

export function useTools() {
  const c = useContext(ToolsCtx);
  if (!c) throw new Error("useTools must be used inside ToolsProvider");
  return c;
}
