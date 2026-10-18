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

export const api = {
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
