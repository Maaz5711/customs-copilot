"use client";
import { AlertTriangle, CheckCircle2, CircleHelp, Info } from "lucide-react";
import { noteText } from "@/lib/api";
import { useReveal } from "@/lib/motion";
import type { Candidate, FinalResult, Note } from "@/lib/types";
import { BillTable, TotalsSummary } from "./BillTable";
import { CandidateCompare } from "./CandidateCompare";
import { Feedback } from "./Feedback";
import { ResearchTrail } from "./ResearchTrail";
import { Card, Notice, Pill } from "./ui";

const fmtCode = (c: string) => (c.length === 8 ? `${c.slice(0, 4)}.${c.slice(4)}` : c);
const conf = (c?: number | null) => (typeof c === "number" ? `${Math.round(c * 100)}% confident` : null);

function Candidates({ list, title }: { list: Candidate[]; title: string }) {
  if (!list.length) return null;
  return (
    <section aria-label={title}>
      <h3 className="mb-2 font-display text-lg font-semibold">{title}</h3>
      <ol className="grid gap-3 md:grid-cols-3">
        {list.map((c, i) => (
          <li key={c.code} data-reveal className="rounded-xl border border-line bg-surface p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="num font-display text-xl font-semibold">{fmtCode(c.code)}</span>
              {conf(c.confidence) && <Pill tone={i === 0 ? "gold" : "neutral"}>{conf(c.confidence)}</Pill>}
            </div>
            {c.description && <p className="mt-1.5 line-clamp-4 text-[15px] text-ink-2">{c.description}</p>}
            {c.source_file && <p className="mt-2 text-xs text-ink-2">Tariff page {c.page ?? "?"}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Where this answer stands, in the order a clearance moves: goods, code, duty, sources, ready to check with Customs. */
function Pipeline({ result }: { result: FinalResult }) {
  const waiting = result.status === "needs_input" && !!result.code;
  const coded = result.status === "answer" || result.status === "cannot_compute" || waiting;
  const steps: [string, "done" | "warn" | "todo", string][] = [
    ["Goods", "done", "described"],
    ["Code", coded ? "done" : result.status === "not_sure" ? "warn" : "todo", coded && result.code ? fmtCode(result.code) : result.status === "not_sure" ? "top candidates" : "not found"],
    ["Duty", result.status === "answer" ? "done" : result.status === "cannot_compute" || waiting ? "warn" : "todo", result.status === "answer" ? "calculated" : result.status === "cannot_compute" ? "partly calculated" : waiting ? "needs a few facts" : "waiting for the code"],
    ["Sources", coded ? "done" : "todo", coded ? "cited per line" : "—"],
    ["Clearance", "todo", "confirm with Customs"],
  ];
  const tone = { done: "border-ok bg-ok text-bg", warn: "border-warn bg-warn-soft text-warn", todo: "border-line bg-surface text-ink-2" };
  return (
    <ol aria-label="Where this answer stands" className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {steps.map(([label, state, note], i) => (
        <li key={label} className="rounded-lg border border-line bg-surface p-2.5">
          <div className="flex items-center gap-2">
            <span className={`inline-flex size-5 items-center justify-center rounded-full border text-[11px] font-bold ${tone[state]}`} aria-hidden="true">{state === "done" ? "✓" : i + 1}</span>
            <span className="text-sm font-semibold">{label}</span>
            <span className="sr-only">: {state === "done" ? "done" : state === "warn" ? "needs attention" : "not done"}</span>
          </div>
          <p className="num mt-1 truncate text-xs text-ink-2">{note}</p>
        </li>
      ))}
    </ol>
  );
}

function List({ title, items, tone }: { title: string; items?: Note[]; tone?: "warn" }) {
  if (!items?.length) return null;
  return (
    <details className="rounded-xl border border-line bg-surface p-4" open={tone === "warn"}>
      <summary className="font-semibold">{title} ({items.length})</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px] text-ink-2">
        {items.map((x, i) => <li key={i}>{noteText(x)}</li>)}
      </ul>
    </details>
  );
}

export function ResultView({ result, threadId, onRestart }: { result: FinalResult; threadId?: string; onRestart: () => void }) {
  const ref = useReveal<HTMLDivElement>(`${threadId}-${result.status}-${result.code}`);
  const cands = result.candidates ?? [];

  return (
    <div ref={ref} className="grid gap-5" aria-live="polite">
      {(result.status === "answer" || result.status === "cannot_compute" || result.status === "not_sure" || result.status === "needs_input") && <Pipeline result={result} />}
      {(result.status === "answer" || result.status === "cannot_compute" || result.status === "not_sure" || result.status === "needs_input") && <ResearchTrail trace={result.trace} />}
      {(result.status === "answer" || result.status === "cannot_compute") && result.code && (
        <>
          <Card data-reveal>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 text-sm font-semibold text-ok"><CheckCircle2 size={18} aria-hidden="true" /> Tariff line found</p>
                <p className="num mt-1 font-display text-3xl font-semibold">{fmtCode(result.code)}</p>
                <p className="mt-1 max-w-3xl text-ink-2">{result.description}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {conf(result.confidence) && <Pill tone="gold">{conf(result.confidence)}</Pill>}
                {result.as_of_date && <Pill>Rules as of {result.as_of_date}</Pill>}
              </div>
            </div>
          </Card>
          {result.status === "cannot_compute" && (
            <Notice tone="warn" title="Part of the bill could not be computed">Some taxes below are missing or partial. Read the notes before using any figure.</Notice>
          )}
          {result.bill?.totals && <TotalsSummary totals={result.bill.totals} />}
          {result.bill && <BillTable lines={result.bill.lines} />}
          {!!result.bill?.optional_lines_not_in_total?.length && (
            <div data-reveal><h3 className="mb-2 font-display text-lg font-semibold">Possible extra charges (not in the total)</h3><BillTable lines={result.bill.optional_lines_not_in_total} /></div>
          )}
          <List title="What is not verified" items={result.unverified} tone="warn" />
          <List title="Flags" items={result.flags} />
          <List title="Assumptions" items={result.assumptions} />
          {result.verification?.summary && <p className="flex gap-2 text-sm text-ink-2"><Info size={18} className="mt-0.5 shrink-0" aria-hidden="true" />Checks run: {result.verification.summary}</p>}
          <Candidates list={cands.slice(1)} title="Other codes I considered" />
          {result.bill && <CandidateCompare chosen={result.code} lines={result.bill.lines} candidates={cands} date={result.as_of_date} />}
        </>
      )}

      {result.status === "not_sure" && (
        <>
          <Notice tone="warn" title="I am not sure about this one">
            <span className="flex items-start gap-2"><CircleHelp size={18} className="mt-0.5 shrink-0" aria-hidden="true" />I would rather say so than guess a code or a rate. These are my top candidates. Check with Pakistan Customs or a licensed customs agent, or describe the product in more detail.</span>
          </Notice>
          <Candidates list={cands} title="Top candidates" />
        </>
      )}

      {result.status === "refused" && <Notice tone="info" title="I can not help with this request">{result.text?.split("\n").filter(Boolean)[0] ?? "This is outside what the tool covers."}</Notice>}
      {result.status === "needs_input" && (
        <>
          {result.code && (
            <Card data-reveal>
              <p className="flex items-center gap-2 text-sm font-semibold text-ok"><CheckCircle2 size={18} aria-hidden="true" /> Tariff line found</p>
              <p className="num mt-1 font-display text-3xl font-semibold">{fmtCode(result.code)}</p>
              {result.description && <p className="mt-1 max-w-3xl text-ink-2">{result.description}</p>}
            </Card>
          )}
          <Notice tone="info" title="Almost there: a few facts are still missing for the bill">
            <p>The rules cannot be applied without these. I will not guess them.</p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              {(result.missing ?? []).map((m, i) => <li key={i}>{m.question}{m.why ? <span className="text-ink-2"> ({m.why})</span> : null}</li>)}
            </ul>
            <p className="mt-2">Ask your clearing agent or the importer, then start a new question and include these details.</p>
          </Notice>
        </>
      )}
      {result.status === "error" && (
        <Notice tone="bad" title="I could not finish this request"><span className="flex gap-2"><AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />Please try again in a minute, or describe the product differently.</span></Notice>
      )}

      {result.text && (
        <details data-reveal className="rounded-xl border border-line bg-surface p-4">
          <summary className="font-semibold">Full written answer with sources</summary>
          <pre className="mt-3 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words font-sans text-[14px] leading-relaxed text-ink-2">{result.text}</pre>
        </details>
      )}

      {(result.status === "answer" || result.status === "cannot_compute" || result.status === "not_sure") && <Feedback threadId={threadId} code={result.code} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-ink-2">{result.disclaimer}</p>
        <button type="button" onClick={onRestart} className="min-h-11 rounded-lg px-3 text-sm font-semibold text-blue underline-offset-2 hover:underline">Start a new question</button>
      </div>
    </div>
  );
}
