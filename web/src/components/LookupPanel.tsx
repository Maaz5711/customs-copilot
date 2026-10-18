"use client";
import { Search } from "lucide-react";
import { useId, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useReveal } from "@/lib/motion";
import type { LookupReply } from "@/lib/types";
import { Button, Card, Field, Notice, Pill, Spinner, TextInput } from "./ui";

const fmtCode = (c: string) => (c.length === 8 ? `${c.slice(0, 4)}.${c.slice(4)}` : c);
type Row = { code: string; description: string; cd: string; page?: number | string };

export function LookupPanel({ date, onPickCode, onAskAgent }: { date: string; onPickCode: (code: string) => void; onAskAgent: (text: string) => void }) {
  const uid = useId();
  const [q, setQ] = useState("");
  const [chapter, setChapter] = useState("");
  const [cd, setCd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState<LookupReply | null>(null);
  const [asked, setAsked] = useState("");
  const ref = useReveal<HTMLDivElement>(reply);

  const search = async () => {
    const query = q.trim();
    if (!query || busy) return;
    setBusy(true); setError(null); setAsked(query);
    try {
      setReply(await api.lookup(query, date, { chapter: chapter.trim() || undefined, cd_pct: cd.trim() || undefined }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  let rows: Row[] = [];
  let heading = "";
  let problem = "";
  if (reply && "mode" in reply) {
    if (reply.mode === "keyword") {
      rows = reply.results.map((r) => ({ code: r.code.replace(".", ""), description: r.description, cd: r.cd_text, page: r.page }));
      heading = `${rows.length} tariff line${rows.length === 1 ? "" : "s"} for “${asked}”`;
      if (reply.status === "no_match") problem = reply.note ?? "No tariff line matched.";
    } else {
      const r = reply.result as Record<string, unknown> & { code?: string; description?: string; cd?: { rate_pct?: string; raw?: string }; page?: number; reason?: string; children?: Row[]; nearest_codes?: { code: string; description: string; cd: string; page: number }[] };
      if (r.code && r.description) rows = [{ code: r.code.replace(".", ""), description: r.description, cd: r.cd?.rate_pct !== undefined ? `${r.cd.rate_pct}%` : r.cd?.raw ?? "see tariff", page: r.page }];
      else if (r.children?.length) rows = r.children.map((c) => ({ code: c.code.replace(".", ""), description: c.description, cd: "", page: c.page }));
      else if (r.nearest_codes?.length) rows = r.nearest_codes.map((c) => ({ code: c.code.replace(".", ""), description: c.description, cd: String(c.cd), page: c.page }));
      heading = r.reason ?? "Tariff line";
      if (!rows.length) problem = r.reason ?? "Nothing found for that code on this date.";
    }
  } else if (reply && "reason" in reply) {
    problem = reply.reason ?? "Please check your input.";
  }

  return (
    <div className="grid gap-5">
      <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); search(); }}>
        <Field label="Product name or code" htmlFor={`${uid}-q`} hint="A word like “laptop” or “lithium battery”, or a code such as 8471.3010 or 8471.">
          <TextInput id={`${uid}-q`} value={q} maxLength={120} onChange={(e) => setQ(e.target.value)} placeholder="laptop computer" autoComplete="off" />
        </Field>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Chapter (optional)" htmlFor={`${uid}-c`}><TextInput id={`${uid}-c`} inputMode="numeric" maxLength={2} value={chapter} onChange={(e) => setChapter(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 85" /></Field>
          <Field label="Customs duty % (optional)" htmlFor={`${uid}-d`}><TextInput id={`${uid}-d`} inputMode="decimal" maxLength={6} value={cd} onChange={(e) => setCd(e.target.value.replace(/[^\d.]/g, ""))} placeholder="e.g. 11" /></Field>
          <button type="submit" disabled={busy || !q.trim()} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">
            <Search size={16} aria-hidden="true" /> Search
          </button>
        </div>
      </form>

      {busy && <Spinner label="Searching the tariff…" />}
      {error && <Notice tone="bad" title="That did not work">{error}</Notice>}

      {reply && !busy && (
        <div ref={ref} className="grid gap-4">
          <p data-reveal className="font-semibold">{heading}</p>
          {problem && <Notice tone="warn">{problem}</Notice>}
          <ul className="grid gap-3">
            {rows.map((r) => (
              <li key={r.code} data-reveal>
                <Card className="grid gap-3 !p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                  <div className="flex items-center gap-3 sm:flex-col sm:items-start sm:gap-1">
                    <span className="num font-display text-xl font-semibold">{fmtCode(r.code)}</span>
                    {r.cd && <Pill tone="gold">Customs duty {r.cd}</Pill>}
                  </div>
                  <p className="text-[15px] text-ink-2">{r.description}{r.page ? <span className="ml-2 text-xs">Tariff page {r.page}</span> : null}</p>
                  {r.code.length === 8 && <Button variant="secondary" onClick={() => onPickCode(r.code)}>Calculate duty</Button>}
                </Card>
              </li>
            ))}
          </ul>
          <div data-reveal className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface-2 p-4">
            <p className="max-w-2xl text-[15px] text-ink-2">This is a keyword search, not a classification. For a code you can rely on, and the full bill, let the agent ask the questions the tariff notes require.</p>
            <Button onClick={() => onAskAgent(asked)}>Ask the agent about this</Button>
          </div>
        </div>
      )}
    </div>
  );
}
