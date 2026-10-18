"use client";
import { useId, useState } from "react";
import type { Question } from "@/lib/types";
import { Button, Notice, TextInput } from "./ui";

const IDK = "I don't know";

function isYesNo(q: Question) {
  return !!q.allowed?.length && q.allowed.every((a) => typeof a === "boolean");
}

// One control per question. Yes/no and fixed choices are radio groups; dates, amounts and free text have their own input. "I don't know" is always an answer.
export function Questions({ questions, message, notes, busy, onSubmit }: {
  questions: Question[]; message?: string | null; notes?: string[]; busy: boolean; onSubmit: (answers: Record<string, string>) => void;
}) {
  const uid = useId();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const set = (id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v }));
  const ready = Object.values(answers).some((v) => v.trim());

  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        const clean = Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim()));
        if (Object.keys(clean).length) onSubmit(clean);
      }}
    >
      <div>
        <h3 className="font-display text-xl font-semibold">{message ?? "I need a little more information"}</h3>
        <p className="mt-1 text-ink-2">Customs rules depend on these facts. Answer what you know. “I don't know” is a valid answer, and I will say what stays uncertain.</p>
      </div>
      {notes?.map((n, i) => <Notice key={i} tone="info">{n}</Notice>)}
      {questions.map((q, i) => {
        const id = `${uid}-${q.id}`;
        const val = answers[q.id] ?? "";
        const options: string[] = isYesNo(q) ? ["Yes", "No"] : (q.allowed ?? []).map(String);
        const grouped = options.length > 0;
        return (
          <fieldset key={q.id} className="grid gap-2 rounded-xl border border-line bg-surface p-4" aria-describedby={q.why ? `${id}-why` : undefined}>
            <legend className="px-1 text-[16px] font-semibold"><span className="mr-2 text-ink-2">{i + 1}.</span>{q.question}</legend>
            {q.why && <p id={`${id}-why`} className="text-sm text-ink-2">Why I ask: {q.why}</p>}
            {q.error && <p className="text-sm text-bad" role="alert">I could not use your last answer: {q.error}</p>}
            {grouped ? (
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={q.question}>
                {[...options, IDK].map((o) => {
                  const v = isYesNo(q) && o !== IDK ? o.toLowerCase() : o;
                  const on = val === v;
                  return (
                    <label key={o} className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3.5 py-2 text-[15px] transition-colors ${on ? "border-blue bg-surface-2 font-semibold" : "border-line hover:bg-surface-2"}`}>
                      <input type="radio" name={id} className="size-4" checked={on} onChange={() => set(q.id, v)} />
                      {o}
                    </label>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-[14rem] flex-1">
                  <TextInput
                    id={id}
                    type={q.type === "date" ? "date" : "text"}
                    inputMode={q.type === "money_pkr" || q.type === "number" || q.type === "quantity" ? "decimal" : undefined}
                    maxLength={500}
                    value={val === IDK ? "" : val}
                    onChange={(e) => set(q.id, e.target.value)}
                    aria-label={q.question}
                    placeholder={q.type === "money_pkr" ? "Amount in PKR, e.g. 2500000" : q.type === "quantity" ? `Number${q.unit ? ` in ${q.unit}` : ""}` : "Type your answer"}
                  />
                </div>
                <Button variant="secondary" onClick={() => set(q.id, IDK)} aria-pressed={val === IDK}>{IDK}</Button>
              </div>
            )}
          </fieldset>
        );
      })}
      <div>
        <button type="submit" disabled={!ready || busy} className="inline-flex min-h-11 items-center justify-center rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">
          {busy ? "Working…" : "Send answers"}
        </button>
      </div>
    </form>
  );
}
