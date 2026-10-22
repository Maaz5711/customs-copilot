"use client";
import { SendHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { AgentReply } from "@/lib/types";
import type { Seed } from "./home/ToolsContext";
import { Questions } from "./Questions";
import { ResultView } from "./ResultView";
import { Thinking } from "./Thinking";
import { Field, Notice } from "./ui";

const EXAMPLES = [
  "Men's cotton T-shirts, new, 5,000 pieces, value PKR 2,500,000",
  "Lithium-ion power bank 10000 mAh",
  "Used diesel generator 6.5 kVA",
];
const MAX = 1500;

export function AgentPanel({ date, seed, variant }: { date: string; seed: Seed; variant?: "hero" }) {
  const hero = variant === "hero";
  const uid = useId();
  const [text, setText] = useState("");
  const [reply, setReply] = useState<AgentReply | null>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [trace, setTrace] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // A seed fills the box; a seed with run (a chip, a common-import card, "Try this product") also asks straight away.
  useEffect(() => {
    if (!seed.n) return;
    setText(seed.text); setReply(null); setError(null);
    if (seed.run && seed.text.trim().length >= 2) { setAsked(seed.text.trim()); run((on) => api.askStream(seed.text.trim(), date, on)); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const run = async (fn: (onStep: (line: string) => void) => Promise<AgentReply>) => {
    setBusy(true); setError(null); setSecs(0); setTrace([]);
    timer.current = setInterval(() => setSecs((s) => s + 1), 1000);
    try {
      setReply(await fn((line) => setTrace((prev) => [...prev, line])));
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
    run((on) => api.askStream(q, date, on));
  };
  const restart = () => { setReply(null); setError(null); setText(""); };

  return (
    <div className="grid gap-5">
      {!reply && (
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); start(); }}>
          <Field label={hero ? "Your goods" : "Describe what you want to import"} htmlFor={`${uid}-q`} hint="Say what it is, what it is made of, what it is for, new or used, and the value if you know it. The more you say, the fewer questions I ask.">
            <textarea
              id={`${uid}-q`}
              className={`w-full resize-y rounded-lg border border-line bg-surface px-3 py-2.5 text-ink placeholder:text-ink-2/70 focus:border-blue ${hero ? "min-h-24 text-[18px]" : "min-h-32 text-[16px]"}`}
              maxLength={MAX}
              value={text}
              placeholder={EXAMPLES[0]}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") start(); }}
            />
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            {hero ? <p className="text-sm text-ink-2">Rules as of <span className="num font-semibold text-ink">{date}</span> · <a href="#tool" className="underline-offset-2 hover:underline">change date</a></p> : (
              <div className="flex flex-wrap items-center gap-2" aria-label="Examples">
                <span className="text-sm text-ink-2">Try:</span>
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" onClick={() => setText(ex)} className="min-h-11 rounded-full border border-line px-3.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
                    {ex.length > 34 ? `${ex.slice(0, 34)}…` : ex}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-center gap-3">
              <span className="num text-sm text-ink-2" aria-hidden="true">{text.length}/{MAX}</span>
              <button type="submit" disabled={busy || text.trim().length < 2} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand transition-opacity hover:opacity-90">
                Find code and duty <SendHorizontal size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </form>
      )}

      {busy && <Thinking trace={trace} secs={secs} />}
      {error && <Notice tone="bad" title="That did not work">{error}</Notice>}

      {reply && !busy && (
        <>
          {asked && <p className="rounded-lg bg-surface-2 px-4 py-3 text-[15px]"><span className="font-semibold">Your product: </span>{asked}</p>}
          {reply.status === "questions" ? (
            <Questions key={reply.questions.map((q) => q.id).join("|")} questions={reply.questions} message={reply.message} notes={reply.notes} busy={busy}
              onSubmit={(answers) => run((on) => api.answerStream(reply.thread_id, answers, on))} />
          ) : (
            <ResultView result={reply.result} threadId={reply.thread_id} onRestart={restart} />
          )}
        </>
      )}
    </div>
  );
}
