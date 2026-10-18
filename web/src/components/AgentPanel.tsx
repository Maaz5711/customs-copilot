"use client";
import { SendHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { AgentReply } from "@/lib/types";
import { Questions } from "./Questions";
import { ResultView } from "./ResultView";
import { Field, Notice, Spinner } from "./ui";

const EXAMPLES = [
  "Men's cotton T-shirts, new, 5,000 pieces, value PKR 2,500,000",
  "Lithium-ion power bank 10000 mAh",
  "Used diesel generator 6.5 kVA",
];
const MAX = 1500;

export function AgentPanel({ date, seed }: { date: string; seed: { text: string; n: number } }) {
  const uid = useId();
  const [text, setText] = useState("");
  const [reply, setReply] = useState<AgentReply | null>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { if (seed.n) { setText(seed.text); setReply(null); setError(null); } }, [seed]);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const run = async (fn: () => Promise<AgentReply>) => {
    setBusy(true); setError(null); setSecs(0);
    timer.current = setInterval(() => setSecs((s) => s + 1), 1000);
    try {
      setReply(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? (e.retryAfter ? `${e.message} (try again in ${e.retryAfter}s)` : e.message) : "Something went wrong.");
    } finally {
      if (timer.current) clearInterval(timer.current);
      setBusy(false);
    }
  };

  const start = () => {
    const q = text.trim();
    if (q.length < 2 || busy) return;
    setAsked(q);
    run(() => api.ask(q, date));
  };
  const restart = () => { setReply(null); setError(null); setText(""); };

  return (
    <div className="grid gap-5">
      {!reply && (
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); start(); }}>
          <Field label="Describe what you want to import" htmlFor={`${uid}-q`} hint="Say what it is, what it is made of, what it is for, new or used, and the value if you know it. The more you say, the fewer questions I ask.">
            <textarea
              id={`${uid}-q`}
              className="min-h-32 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2.5 text-[16px] text-ink placeholder:text-ink-2/70 focus:border-blue"
              maxLength={MAX}
              value={text}
              placeholder={EXAMPLES[0]}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") start(); }}
            />
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2" aria-label="Examples">
              <span className="text-sm text-ink-2">Try:</span>
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setText(ex)} className="min-h-11 rounded-full border border-line px-3.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
                  {ex.length > 34 ? `${ex.slice(0, 34)}…` : ex}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <span className="num text-sm text-ink-2" aria-hidden="true">{text.length}/{MAX}</span>
              <button type="submit" disabled={busy || text.trim().length < 2} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">
                Find code and duty <SendHorizontal size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </form>
      )}

      {busy && <Spinner label={`Working on it… ${secs}s. A new question can take up to a minute.`} />}
      {error && <Notice tone="bad" title="That did not work">{error}</Notice>}

      {reply && !busy && (
        <>
          {asked && <p className="rounded-lg bg-surface-2 px-4 py-3 text-[15px]"><span className="font-semibold">Your product: </span>{asked}</p>}
          {reply.status === "questions" ? (
            <Questions key={reply.questions.map((q) => q.id).join("|")} questions={reply.questions} message={reply.message} notes={reply.notes} busy={busy}
              onSubmit={(answers) => run(() => api.answer(reply.thread_id, answers))} />
          ) : (
            <ResultView result={reply.result} threadId={reply.thread_id} onRestart={restart} />
          )}
        </>
      )}
    </div>
  );
}
