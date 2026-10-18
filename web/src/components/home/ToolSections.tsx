"use client";
import { Calculator, MessageSquareText, Search } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useId, useState } from "react";
import { api } from "@/lib/api";
import type { Meta } from "@/lib/types";
import { AgentPanel } from "../AgentPanel";
import { BillPanel } from "../BillPanel";
import { LookupPanel } from "../LookupPanel";
import { glideTo } from "../SmoothScroll";
import { Field, TextInput } from "../ui";

// The three tools, each in its own section of the home page (describe a product is the main one). One "rules as of" date applies to all three.
// Cross-links move the visitor between them: a looked-up code opens in the calculator, a keyword can be handed to the agent.

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const go = (id: string) => {
  const el = document.getElementById(id);
  if (el) glideTo(el.getBoundingClientRect().top + window.scrollY - 12);
};

function ToolBlock({ id, step, icon, title, lead, main, children }: { id: string; step: string; icon: ReactNode; title: string; lead: string; main?: boolean; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className={`scroll-mt-6 rounded-2xl border bg-surface shadow-[0_1px_0_rgba(15,23,42,0.04),0_12px_32px_-18px_rgba(15,23,42,0.25)] ${main ? "border-gold/60" : "border-line"}`}>
      <div className="flex flex-wrap items-start gap-3 border-b border-line px-4 py-4 sm:px-6">
        <span className={`inline-flex size-10 shrink-0 items-center justify-center rounded-xl ${main ? "bg-gold-soft text-gold" : "bg-surface-2 text-ink"}`} aria-hidden="true">{icon}</span>
        <div className="min-w-0 flex-1">
          <p className="hud-label">{step}{main && <span className="ml-2 rounded-full bg-gold-soft px-2 py-0.5 text-gold">Main tool</span>}</p>
          <h2 id={`${id}-h`} className="mt-0.5 font-display text-2xl font-semibold sm:text-[1.7rem]">{title}</h2>
          <p className="mt-1 max-w-3xl text-ink-2">{lead}</p>
        </div>
      </div>
      <div className="p-4 sm:p-6">{children}</div>
    </section>
  );
}

export function ToolSections() {
  const uid = useId();
  const [date, setDate] = useState(localToday());
  const [meta, setMeta] = useState<Meta | null>(null);
  const [seed, setSeed] = useState({ text: "", n: 0 });
  const [codeSeed, setCodeSeed] = useState({ value: "", n: 0 });

  useEffect(() => {
    api.meta().then((m) => { setMeta(m); setDate(m.today); }).catch(() => {});
  }, []);

  // "Try this product" buttons in the story fill the describe box with their example.
  useEffect(() => {
    const onTry = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text === "string" && text) setSeed((s) => ({ text, n: s.n + 1 }));
    };
    window.addEventListener("cc:try", onTry);
    return () => window.removeEventListener("cc:try", onTry);
  }, []);

  const outside = meta && (date < meta.covers_from || date > meta.covers_to);

  return (
    <div id="tool" className="grid scroll-mt-6 gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-line bg-surface-2/60 px-4 py-4 sm:px-6">
        <div className="max-w-2xl">
          <h2 className="font-display text-xl font-semibold">Three tools, one set of rules</h2>
          <p className="text-[15px] text-ink-2">Pick the date your goods are assessed. All three tools use the rules in force on that date (FY2025-26 and FY2026-27).</p>
        </div>
        <Field label="Rules as of" htmlFor={`${uid}-date`}>
          <TextInput id={`${uid}-date`} type="date" className="!min-h-10 !py-1 w-44" value={date} min={meta?.covers_from} max={meta?.covers_to} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </Field>
        {outside && <p className="w-full rounded-lg bg-warn-soft px-4 py-3 text-[15px] text-warn" role="alert">This date is outside what the tool covers ({meta!.covers_from} to {meta!.covers_to}).</p>}
      </div>

      <ToolBlock id="describe" step="Tool 1" main icon={<MessageSquareText size={20} />} title="Describe a product"
        lead="Say what you are importing in plain words. It asks the questions the tariff needs, finds the 8-digit PCT code (or shows its top 3 when unsure) and builds the full bill with a source for every figure.">
        <AgentPanel date={date} seed={seed} />
      </ToolBlock>

      <ToolBlock id="lookup" step="Tool 2" icon={<Search size={20} />} title="Look up a code"
        lead="Know the code, or a keyword from the tariff? Search all 8-digit lines with their customs duty and tariff page, then send a line to the calculator.">
        <LookupPanel date={date} onPickCode={(c) => { setCodeSeed((s) => ({ value: c, n: s.n + 1 })); go("calculate"); }} onAskAgent={(t) => { setSeed((s) => ({ text: t, n: s.n + 1 })); go("describe"); }} />
      </ToolBlock>

      <ToolBlock id="calculate" step="Tool 3" icon={<Calculator size={20} />} title="Calculate duty"
        lead="Have the code and the value? Get every duty and tax on the date you chose: customs duty, regulatory duty, additional customs duty, sales tax, further tax, value addition tax, income tax and FED, each with its source.">
        <BillPanel date={date} code={codeSeed} />
      </ToolBlock>
    </div>
  );
}
