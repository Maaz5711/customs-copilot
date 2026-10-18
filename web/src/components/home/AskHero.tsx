"use client";
import { BadgeCheck, Calculator, CalendarClock, Cpu, Factory, Car, House, ScrollText, ShieldCheck, Shirt, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { AgentPanel } from "../AgentPanel";
import { useTools } from "./ToolsContext";

// The first screen: one question, "What are you importing?", answered right here by the agent (code, questions if needed, the full cited bill).
// Chips and the common-imports cards fill the box and start at once. The scroll story follows below as "How it works".

const CHIPS = ["Solar panels from China", "Laptop for my shop", "Used car 1300cc", "Kapray import karne par duty kitni?"];

const TRUST: [ReactNode, string][] = [
  [<ScrollText key="i" size={17} />, "Every figure names its FBR source"],
  [<Calculator key="i" size={17} />, "Exact arithmetic, never the AI"],
  [<CalendarClock key="i" size={17} />, "Rules for the date you choose"],
  [<ShieldCheck key="i" size={17} />, "No sign-up; nothing kept beyond an hour"],
];

// Starter questions per kind of import. Mobile phones are left out on purpose: their tax table is not computed yet.
const BROWSE: [ReactNode, string, string[]][] = [
  [<Cpu key="i" size={20} />, "Electronics", ["Laptop 15.6 inch for resale", "Lithium-ion power bank 10,000 mAh", "LED TV 43 inch for my shop"]],
  [<Sun key="i" size={20} />, "Solar", ["Solar panels 550 W from China", "Hybrid solar inverter 6 kW", "Lithium battery for solar, 5 kWh"]],
  [<Car key="i" size={20} />, "Vehicles and parts", ["Used car 1300cc, 3 years old", "Car tyres 195/65 R15, new", "Brake pads for motorcycles"]],
  [<Shirt key="i" size={20} />, "Textiles", ["Cotton bedsheets for resale", "Polyester yarn for weaving", "Ladies' woollen shawls"]],
  [<Factory key="i" size={20} />, "Machinery", ["Industrial sewing machine", "Air compressor 10 HP", "Parts for a CNC milling machine"]],
  [<House key="i" size={20} />, "Home and personal", ["Kitchen blender for home use", "Treadmill for home gym", "Baby stroller"]],
];

export function AskHero() {
  const { date, seed, ask } = useTools();
  return (
    <section id="ask" aria-labelledby="ask-h" className="ask-hero scroll-mt-24">
      <div className="mx-auto max-w-4xl px-4 pb-10 pt-12 sm:px-6 sm:pt-16">
        <p className="hud-label text-center text-gold">Pakistan customs duty calculator · independent</p>
        <h1 id="ask-h" className="mt-2 text-center font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">What are you importing?</h1>
        <p className="mx-auto mt-4 max-w-2xl text-center text-[17px] text-ink-2">
          Describe it in your own words, in English or Roman Urdu. You get the 8-digit PCT code and the full duty and tax bill, with the FBR source of every figure.
        </p>

        <div className="ask-box mt-7 rounded-2xl border border-line bg-surface p-4 shadow-[0_18px_50px_-28px_rgba(15,23,42,0.45)] sm:p-5">
          <AgentPanel date={date} seed={seed} variant="hero" />
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-2" aria-label="Example questions">
          {CHIPS.map((c) => (
            <button key={c} type="button" onClick={() => ask(c)} className="min-h-11 rounded-full border border-line bg-surface px-4 text-[14px] text-ink-2 transition-colors hover:border-gold hover:text-ink">{c}</button>
          ))}
        </div>

        <ul className="mt-8 grid grid-cols-1 gap-2 text-[14px] sm:grid-cols-2 lg:grid-cols-4" aria-label="Why you can trust the answer">
          {TRUST.map(([icon, t]) => (
            <li key={t} className="flex items-center gap-2 rounded-lg bg-surface-2/70 px-3 py-2.5 text-ink"><span className="text-ok" aria-hidden="true">{icon}</span>{t}</li>
          ))}
        </ul>
      </div>

      <div className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <h2 className="flex items-center gap-2 font-display text-2xl font-semibold"><BadgeCheck size={22} className="text-gold" aria-hidden="true" /> Or start from a common import</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {BROWSE.map(([icon, title, qs]) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-4">
              <p className="flex items-center gap-2 font-display text-lg font-semibold"><span className="inline-flex size-9 items-center justify-center rounded-lg bg-gold-soft text-gold" aria-hidden="true">{icon}</span>{title}</p>
              <ul className="mt-3 grid gap-1.5">
                {qs.map((q) => (
                  <li key={q}>
                    <button type="button" onClick={() => ask(q)} className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 text-left text-[15px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
                      {q} <span aria-hidden="true">→</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-3 text-sm text-ink-2">Mobile phones are not covered yet: their tax table is not computed by this tool.</p>
      </div>
    </section>
  );
}
