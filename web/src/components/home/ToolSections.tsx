"use client";
import { Calculator, MessageSquareText, Search } from "lucide-react";
import type { ReactNode } from "react";
import { useId } from "react";
import { BillPanel } from "../BillPanel";
import { LookupPanel } from "../LookupPanel";
import { Field, TextInput } from "../ui";
import { useTools } from "./ToolsContext";

// The tools part of the home page: a three-way picker (describe a product lives in the search box at the top), the one shared
// "rules as of" date, then the code lookup and the duty calculator in their own sections. Cross-links move between them.

function ToolBlock({ id, step, icon, title, lead, children }: { id: string; step: string; icon: ReactNode; title: string; lead: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-24 rounded-2xl border border-line bg-surface shadow-[0_1px_0_rgba(15,23,42,0.04),0_12px_32px_-18px_rgba(15,23,42,0.25)]">
      <div className="flex flex-wrap items-start gap-3 border-b border-line px-4 py-4 sm:px-6">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-ink" aria-hidden="true">{icon}</span>
        <div className="min-w-0 flex-1">
          <p className="hud-label">{step}</p>
          <h2 id={`${id}-h`} className="mt-0.5 font-display text-2xl font-semibold sm:text-[1.7rem]">{title}</h2>
          <p className="mt-1 max-w-3xl text-ink-2">{lead}</p>
        </div>
      </div>
      <div className="p-4 sm:p-6">{children}</div>
    </section>
  );
}

const PICKS = [
  ["ask", MessageSquareText, "Describe a product", "You know what the goods are, not the code. Get the code and the full bill."],
  ["lookup", Search, "Look up a code", "You know the code or a tariff keyword. See the line, its duty and its page."],
  ["calculate", Calculator, "Calculate duty", "You have the code and the value. Get every duty and tax with sources."],
] as const;

export function ToolSections() {
  const uid = useId();
  const { date, setDate, meta, ask, codeSeed, calc, go } = useTools();
  const outside = meta && (date < meta.covers_from || date > meta.covers_to);

  return (
    <div id="tool" className="grid scroll-mt-24 gap-8">
      <div>
        <p className="hud-label text-gold">The tools</p>
        <h2 className="mt-1 font-display text-3xl font-semibold leading-tight sm:text-4xl">What do you want to do?</h2>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {PICKS.map(([id, Icon, title, when], i) => (
            <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); go(id); }}
              className={`group flex min-h-24 items-start gap-3 rounded-xl border p-4 transition-colors hover:border-gold hover:bg-gold-soft/40 ${i === 0 ? "border-gold/60 bg-surface" : "border-line bg-surface"}`}>
              <span className={`inline-flex size-10 shrink-0 items-center justify-center rounded-xl ${i === 0 ? "bg-gold-soft text-gold" : "bg-surface-2 text-ink"}`} aria-hidden="true"><Icon size={20} /></span>
              <span>
                <span className="block font-display text-lg font-semibold">{title} <span aria-hidden="true" className="inline-block transition-transform group-hover:translate-x-1">→</span></span>
                <span className="block text-[15px] text-ink-2">{when}</span>
              </span>
            </a>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-line bg-surface-2/60 px-4 py-4 sm:px-6">
        <div className="max-w-2xl">
          <h3 className="font-display text-lg font-semibold">One date for every tool</h3>
          <p className="text-[15px] text-ink-2">Pick the date your goods are assessed. The search box, the lookup and the calculator all use the rules in force on that date (FY2025-26 and FY2026-27).</p>
        </div>
        <Field label="Rules as of" htmlFor={`${uid}-date`}>
          <TextInput id={`${uid}-date`} type="date" className="!min-h-10 !py-1 w-44" value={date} min={meta?.covers_from} max={meta?.covers_to} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </Field>
        {outside && <p className="w-full rounded-lg bg-warn-soft px-4 py-3 text-[15px] text-warn" role="alert">This date is outside what the tool covers ({meta!.covers_from} to {meta!.covers_to}).</p>}
      </div>

      <ToolBlock id="lookup" step="Tool 2" icon={<Search size={20} />} title="Look up a code"
        lead="Know the code, or a keyword from the tariff? Search all 8-digit lines with their customs duty and tariff page, then send a line to the calculator.">
        <LookupPanel date={date} onPickCode={calc} onAskAgent={ask} />
      </ToolBlock>

      <ToolBlock id="calculate" step="Tool 3" icon={<Calculator size={20} />} title="Calculate duty"
        lead="Have the code and the value? Get every duty and tax on the date you chose: customs duty, regulatory duty, additional customs duty, sales tax, further tax, value addition tax, income tax and FED, each with its source.">
        <BillPanel date={date} code={codeSeed} />
      </ToolBlock>
    </div>
  );
}
