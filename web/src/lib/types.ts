// Shapes returned by the Python API (src/api). Optional fields are optional because the agent leaves them out in some situations.

// The API sends notes either as plain text or as {id, text}; noteText() in api.ts turns both into text.
export type Note = string | { id?: string; text?: string; [k: string]: unknown };

export type Question = {
  id: string;
  question: string;
  why?: string | null;
  type?: string | null; // "date" | "money_pkr" | "number" | "quantity" | "text" ...
  allowed?: (string | boolean)[] | null;
  unit?: string | null;
  error?: string | null;
};

export type Candidate = {
  code: string;
  description?: string;
  confidence?: number;
  reasons?: string[] | string;
  source_file?: string;
  page?: number | string;
};

export type BillLine = {
  tax: string;
  label: string;
  rate?: { kind: string; pct?: string; amount_pkr?: string; unit?: string } | null;
  base_label?: string;
  base_pkr?: string;
  amount_pkr: string;
  instrument?: string;
  clause?: string;
  source_file?: string;
  page?: number | string;
  valid_from?: string;
  valid_to?: string;
  status?: string;
  flags?: Note[];
  assumptions?: Note[];
  included_in_total?: boolean;
};

export type Totals = {
  customs_duties: string;
  federal_excise_duty: string;
  sales_tax: string;
  income_tax: string;
  total_payable_pkr: string;
};

export type Citation = { kind?: string; code?: string; source_file?: string; page?: number | string; sro?: string; clause?: string; text?: string };

export type MissingInput = { field: string; question: string; why?: string; allowed?: (string | boolean)[]; affects?: string[] };

export type Bill = {
  lines: BillLine[];
  totals: Totals | null;
  optional_lines_not_in_total?: BillLine[];
  partial_total_of_computed_lines_pkr?: string | null;
};

export type FinalResult = {
  status: "answer" | "cannot_compute" | "not_sure" | "refused" | "error" | "needs_input";
  text?: string;
  code?: string | null;
  description?: string;
  as_of_date?: string;
  confidence?: number | null;
  candidates?: Candidate[];
  bill?: Bill | null;
  citations?: Citation[];
  flags?: Note[];
  assumptions?: Note[];
  unverified?: Note[];
  verification?: { summary?: string; warnings?: Note[] } | null;
  disclaimer?: string;
};

export type AgentReply =
  | { status: "questions"; thread_id: string; message?: string | null; notes: string[]; questions: Question[] }
  | { status: FinalResult["status"]; thread_id: string; result: FinalResult };

export type LookupRow = {
  rank: number;
  code: string;
  description: string;
  chapter: string;
  cd_text: string;
  fy: string;
  source_file: string;
  page: number | string;
  flags: string[];
};

export type LookupReply =
  | { status: "ok" | "no_match"; mode: "keyword"; as_of_date: string; query: string; results: LookupRow[]; note?: string | null; agent_hint: string }
  | { status: string; mode: "code"; as_of_date: string; result: Record<string, unknown>; agent_hint: string }
  | { status: "invalid_input" | "date_outside_store"; reason?: string };

export type BillReply = {
  status: "computed" | "needs_input" | "cannot_compute" | string;
  code?: string;
  description?: string;
  as_of_date?: string;
  lines?: BillLine[];
  totals?: Totals | null;
  missing_inputs?: MissingInput[];
  flags?: Note[];
  assumptions?: Note[];
  notes?: Note[];
  concessions?: Record<string, unknown>;
  reason?: string;
};

export type Meta = { covers_from: string; covers_to: string; today: string; disclaimer: string };
