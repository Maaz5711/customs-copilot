import type { AgentReply, BillReply, LookupReply, Meta, Note } from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number, public retryAfter?: number) {
    super(message);
  }
}

// One small typed client. It never logs what the user typed, and it gives up after a limit so a stuck request cannot hang the page.
async function call<T>(path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctl.signal,
      cache: "no-store",
      credentials: "omit",
    });
    if (res.status === 204) return undefined as T;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data?.message === "string" ? data.message : "Something went wrong. Please try again.";
      throw new ApiError(msg, res.status, Number(res.headers.get("retry-after")) || undefined);
    }
    return data as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === "AbortError") throw new ApiError("This is taking too long. Please try again.", 0);
    throw new ApiError("Could not reach the service. Check your connection and try again.", 0);
  } finally {
    clearTimeout(timer);
  }
}

const NL = String.fromCharCode(10);          // the stream sends one JSON object per line

type StreamEvent ={ type: "step"; node: string; text: string } | { type: "done"; reply: AgentReply } | { type: "error"; status: number; message: string };

// The agent's live progress arrives as one JSON object per line. onStep gets each step as it happens; the promise resolves with the final reply.
async function stream(path: string, body: unknown, onStep: (line: string) => void, timeoutMs = 180_000): Promise<AgentReply> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal, cache: "no-store", credentials: "omit" });
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(typeof data?.message === "string" ? data.message : "Something went wrong. Please try again.", res.status, Number(res.headers.get("retry-after")) || undefined);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let reply: AgentReply | null = null;
    const handle = (line: string) => {
      if (!line.trim()) return;
      const ev = JSON.parse(line) as StreamEvent;
      if (ev.type === "step") onStep(ev.text);
      else if (ev.type === "done") reply = ev.reply;
      else if (ev.type === "error") throw new ApiError(ev.message, ev.status);
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let i = buf.indexOf(NL);
      while (i >= 0) { handle(buf.slice(0, i)); buf = buf.slice(i + 1); i = buf.indexOf(NL); }
    }
    handle(buf);
    if (!reply) throw new ApiError("The answer was cut off. Please try again.", 0);
    return reply;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === "AbortError") throw new ApiError("This is taking too long. Please try again.", 0);
    throw new ApiError("Could not reach the service. Check your connection and try again.", 0);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  askStream: (question: string, date: string, onStep: (line: string) => void) => stream("/api/agent/ask/stream", { question, date }, onStep),
  answerStream: (thread_id: string, answers: Record<string, string>, onStep: (line: string) => void) => stream("/api/agent/answer/stream", { thread_id, answers }, onStep),
  meta: () => call<Meta>("/api/meta", undefined, 15_000),
  ask: (question: string, date: string) => call<AgentReply>("/api/agent/ask", { question, date }),
  answer: (thread_id: string, answers: Record<string, string>) => call<AgentReply>("/api/agent/answer", { thread_id, answers }),
  lookup: (query: string, date: string, opts: { chapter?: string; cd_pct?: string; k?: number } = {}) =>
    call<LookupReply>("/api/lookup", { query, date, k: opts.k ?? 10, ...(opts.chapter ? { chapter: opts.chapter } : {}), ...(opts.cd_pct ? { cd_pct: opts.cd_pct } : {}) }, 60_000),
  bill: (payload: Record<string, unknown>) => call<BillReply>("/api/bill", payload, 60_000),
  feedback: (payload: { helpful: boolean; thread_id?: string; code?: string; note?: string; consent_to_store_note?: boolean }) =>
    call<void>("/api/feedback", payload, 15_000),
};

// Notes arrive as text or as {id, text}; show the text, or a readable form of the id.
export const noteText = (n: Note): string => (typeof n === "string" ? n : (n.text ?? String(n.id ?? "")).toString().replaceAll("_", " "));

export const pkr = (v: string | number | null | undefined) => {
  if (v === null || v === undefined || v === "") return "–";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v);
};
