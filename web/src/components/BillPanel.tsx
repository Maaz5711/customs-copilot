"use client";
import { Calculator } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ApiError, api, noteText } from "@/lib/api";
import { useReveal } from "@/lib/motion";
import type { BillReply, MissingInput } from "@/lib/types";
import { BillTable, TotalsSummary } from "./BillTable";
import { Field, Notice, Spinner, TextInput, inputClass } from "./ui";

const YESNO = ["yes", "no"] as const;
const parse = (v: string) => (v === "yes" ? true : v === "no" ? false : v);

// For people who already know the code. The same exact calculator the agent uses; it asks for any importer fact it still needs.
export function BillPanel({ date, code: seedCode }: { date: string; code: { value: string; n: number } }) {
  const uid = useId();
  const [code, setCode] = useState("");
  const [value, setValue] = useState("");
  const [registration, setRegistration] = useState("registered");
  const [commercial, setCommercial] = useState("yes");
  const [active, setActive] = useState("yes");
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<BillReply | null>(null);
  const ref = useReveal<HTMLDivElement>(res);

  useEffect(() => { if (seedCode.n) { setCode(seedCode.value); setRes(null); setExtra({}); } }, [seedCode]);

  const calc = async () => {
    const v = Number(value.replace(/,/g, ""));
    if (!code.trim() || !Number.isFinite(v) || v <= 0 || busy) return;
    const importer: Record<string, string | boolean> = { registration_status: registration, commercial_importer: commercial === "yes", active_taxpayer: active === "yes" };
    const goods: Record<string, string | boolean> = {};
    for (const [field, val] of Object.entries(extra)) {
      if (!val) continue;
      const [scope, ...rest] = field.split(".");
      (scope === "goods" ? goods : importer)[rest.join(".") || field] = parse(val);
    }
    setBusy(true); setError(null);
    try {
      setRes(await api.bill({ code: code.trim(), value_pkr: v, date, importer, goods }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const missing: MissingInput[] = res?.status === "needs_input" ? res.missing_inputs ?? [] : [];

  return (
    <div className="grid gap-5">
      <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); calc(); }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tariff code (8 digits)" htmlFor={`${uid}-code`}><TextInput id={`${uid}-code`} value={code} maxLength={11} inputMode="numeric" onChange={(e) => setCode(e.target.value)} placeholder="8471.3010" /></Field>
          <Field label="Assessable value (PKR)" htmlFor={`${uid}-v`} hint="The customs value of the goods in rupees, as Customs will assess it."><TextInput id={`${uid}-v`} value={value} inputMode="decimal" maxLength={16} onChange={(e) => setValue(e.target.value)} placeholder="1,000,000" /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Sales tax registration" htmlFor={`${uid}-r`}>
            <select id={`${uid}-r`} className={inputClass} value={registration} onChange={(e) => setRegistration(e.target.value)}><option value="registered">Registered</option><option value="unregistered">Unregistered</option></select>
          </Field>
          <Field label="Commercial importer" htmlFor={`${uid}-ci`}>
            <select id={`${uid}-ci`} className={inputClass} value={commercial} onChange={(e) => setCommercial(e.target.value)}><option value="yes">Yes (imports to sell)</option><option value="no">No (own use or industrial)</option></select>
          </Field>
          <Field label="On FBR Active Taxpayers List" htmlFor={`${uid}-a`} hint="If not, income tax is doubled.">
            <select id={`${uid}-a`} className={inputClass} value={active} onChange={(e) => setActive(e.target.value)}><option value="yes">Yes</option><option value="no">No</option></select>
          </Field>
        </div>

        {missing.map((m) => (
          <Field key={m.field} label={m.question} htmlFor={`${uid}-${m.field}`} hint={m.why}>
            {m.allowed?.every((a) => typeof a === "boolean") ? (
              <select id={`${uid}-${m.field}`} className={inputClass} value={extra[m.field] ?? ""} onChange={(e) => setExtra((x) => ({ ...x, [m.field]: e.target.value }))}>
                <option value="">Choose…</option>{YESNO.map((o) => <option key={o} value={o}>{o === "yes" ? "Yes" : "No"}</option>)}
              </select>
            ) : (
              <TextInput id={`${uid}-${m.field}`} maxLength={200} value={extra[m.field] ?? ""} onChange={(e) => setExtra((x) => ({ ...x, [m.field]: e.target.value }))} />
            )}
          </Field>
        ))}

        <div>
          <button type="submit" disabled={busy || !code.trim() || !value.trim()} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">
            <Calculator size={16} aria-hidden="true" /> {missing.length ? "Recalculate" : "Calculate duty"}
          </button>
        </div>
      </form>

      {busy && <Spinner label="Calculating…" />}
      {error && <Notice tone="bad" title="That did not work">{error}</Notice>}

      {res && !busy && (
        <div ref={ref} className="grid gap-5">
          {res.status === "needs_input" && <Notice tone="warn" title="One more fact is needed">Answer the question above and press Recalculate. I do not guess these.</Notice>}
          {res.status === "cannot_compute" && <Notice tone="warn" title="Part of the bill cannot be computed">{res.reason ?? "Some charges below are missing. Read the notes before using any figure."}</Notice>}
          {["not_found", "invalid_input", "date_outside_store"].includes(res.status) && <Notice tone="bad" title="Check the code or date">{res.reason ?? "That code was not found for this date."}</Notice>}
          {res.totals && res.status === "computed" && <TotalsSummary totals={res.totals} />}
          {!!res.lines?.length && <BillTable lines={res.lines} />}
          {!!res.flags?.length && <Notice tone="warn" title="Flags">{res.flags.map(noteText).join(" · ")}</Notice>}
          {!!res.assumptions?.length && (
            <details className="rounded-xl border border-line bg-surface p-4"><summary className="font-semibold">Assumptions ({res.assumptions.length})</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px] text-ink-2">{res.assumptions.map((a, i) => <li key={i}>{noteText(a)}</li>)}</ul></details>
          )}
          <p className="text-sm text-ink-2">Rules as of {res.as_of_date ?? date}. Duty arithmetic is exact; the code, value and importer facts are what you entered.</p>
        </div>
      )}
    </div>
  );
}
