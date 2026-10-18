"use client";
import { Calculator, MessageSquareText, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Meta } from "@/lib/types";
import { AgentPanel } from "./AgentPanel";
import { BillPanel } from "./BillPanel";
import { LookupPanel } from "./LookupPanel";
import { Field, TextInput } from "./ui";

const TABS = [
  { id: "agent", label: "Describe a product", icon: MessageSquareText },
  { id: "lookup", label: "Look up a code", icon: Search },
  { id: "bill", label: "Calculate duty", icon: Calculator },
] as const;
type TabId = (typeof TABS)[number]["id"];

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function Tool() {
  const uid = useId();
  const [tab, setTab] = useState<TabId>("agent");
  const [date, setDate] = useState(localToday());
  const [meta, setMeta] = useState<Meta | null>(null);
  const [seed, setSeed] = useState({ text: "", n: 0 });
  const [codeSeed, setCodeSeed] = useState({ value: "", n: 0 });
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    api.meta().then((m) => { setMeta(m); setDate(m.today); }).catch(() => {});
  }, []);

  const onKey = (e: React.KeyboardEvent) => {
    const i = TABS.findIndex((t) => t.id === tab);
    const j = e.key === "ArrowRight" ? (i + 1) % TABS.length : e.key === "ArrowLeft" ? (i + TABS.length - 1) % TABS.length : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : -1;
    if (j < 0) return;
    e.preventDefault();
    const next = TABS[j]!;
    setTab(next.id);
    refs.current[next.id]?.focus();
  };

  return (
    <section aria-label="Customs tool" className="rounded-2xl border border-line bg-surface shadow-[0_1px_0_rgba(15,23,42,0.04),0_12px_32px_-18px_rgba(15,23,42,0.25)]">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-4 pt-3 sm:px-6">
        <div role="tablist" aria-label="Choose how to work" className="-mb-px flex flex-wrap gap-1" onKeyDown={onKey}>
          {TABS.map(({ id, label, icon: Icon }) => {
            const on = tab === id;
            return (
              <button key={id} ref={(el) => { refs.current[id] = el; }} role="tab" id={`${uid}-tab-${id}`} aria-selected={on} aria-controls={`${uid}-panel-${id}`} tabIndex={on ? 0 : -1} type="button" onClick={() => setTab(id)}
                className={`inline-flex min-h-11 items-center gap-2 border-b-2 px-3.5 py-2 text-[15px] font-semibold transition-colors ${on ? "border-blue text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}>
                <Icon size={17} aria-hidden="true" /> {label}
              </button>
            );
          })}
        </div>
        <div className="pb-2.5">
          <Field label="Rules as of" htmlFor={`${uid}-date`}>
            <TextInput id={`${uid}-date`} type="date" className="!min-h-10 !py-1 w-44" value={date} min={meta?.covers_from} max={meta?.covers_to} onChange={(e) => e.target.value && setDate(e.target.value)} />
          </Field>
        </div>
      </div>

      <div className="p-4 sm:p-6">
        {meta && (date < meta.covers_from || date > meta.covers_to) && (
          <p className="mb-4 rounded-lg bg-warn-soft px-4 py-3 text-[15px] text-warn" role="alert">This date is outside what the tool covers ({meta.covers_from} to {meta.covers_to}).</p>
        )}
        <div role="tabpanel" id={`${uid}-panel-agent`} aria-labelledby={`${uid}-tab-agent`} hidden={tab !== "agent"}><AgentPanel date={date} seed={seed} /></div>
        <div role="tabpanel" id={`${uid}-panel-lookup`} aria-labelledby={`${uid}-tab-lookup`} hidden={tab !== "lookup"}>
          <LookupPanel date={date} onPickCode={(c) => { setCodeSeed((s) => ({ value: c, n: s.n + 1 })); setTab("bill"); }} onAskAgent={(t) => { setSeed((s) => ({ text: t, n: s.n + 1 })); setTab("agent"); }} />
        </div>
        <div role="tabpanel" id={`${uid}-panel-bill`} aria-labelledby={`${uid}-tab-bill`} hidden={tab !== "bill"}><BillPanel date={date} code={codeSeed} /></div>
      </div>
    </section>
  );
}
