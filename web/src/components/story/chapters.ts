// The scroll story: what each chapter says, when it plays (scroll progress 0..1 through the pinned stage), and the example it shows.
// The example is a real run of the tool (power bank, 10,000 mAh, assessed value PKR 500,000, registered commercial importer, rules as of
// 18 Oct 2026), so every figure and source below is what the tool actually produced, not an illustration.

export type Chapter = {
  id: string;
  from: number;
  to: number;
  kicker: string;
  title: string;
  body: string;
  step: string; // the checklist line this chapter completes
};

export const CHAPTERS: Chapter[] = [
  {
    id: "arrive",
    from: 0,
    to: 0.14,
    kicker: "Pakistan customs · import duty and tax",
    title: "The right customs code, and the whole bill behind it.",
    body: "Describe what you are importing. Customs Copilot finds the tariff line and works out every duty and tax, with the source of each figure.",
    step: "Goods described",
  },
  {
    id: "code",
    from: 0.14,
    to: 0.3,
    kicker: "1 · Find the tariff line",
    title: "The goods get a code.",
    body: "It asks the questions the tariff notes require, then searches 7,605 tariff lines, the legal notes and past rulings, and a separate check reviews the choice.",
    step: "Tariff line found",
  },
  {
    id: "bill",
    from: 0.3,
    to: 0.52,
    kicker: "2 · Work out the bill",
    title: "The bill builds, layer by layer.",
    body: "Customs duty, regulatory duty, additional duty, sales tax, value addition tax and income tax. The arithmetic is exact code, never the AI.",
    step: "Duty and tax calculated",
  },
  {
    id: "sources",
    from: 0.52,
    to: 0.68,
    kicker: "3 · Show the evidence",
    title: "Every figure shows its source.",
    body: "Each rate points to the tariff page or notification it came from, and the answer lists what it could not verify.",
    step: "Sources cited",
  },
  {
    id: "unsure",
    from: 0.68,
    to: 0.82,
    kicker: "4 · Be honest about doubt",
    title: "When it is not sure, it says so.",
    body: "If the evidence stays thin after two retries, it shows its top candidates and asks you to check, instead of guessing a code or a rate.",
    step: "Doubt flagged, never guessed",
  },
  {
    id: "clear",
    from: 0.82,
    to: 1,
    kicker: "Your turn",
    title: "Cleared. Now try your own goods.",
    body: "Describe a product, look up a code, or calculate a bill. Rules as of the date you choose, for FY2025-26 and FY2026-27.",
    step: "Ready for your goods",
  },
];

export const EXAMPLE = {
  product: "Lithium-ion power bank, 10,000 mAh",
  code: "8507.6000",
  codeName: "Electric accumulators > Lithium-ion",
  value: 500000,
  asOf: "18 Oct 2026",
  who: "registered commercial importer",
  questions: [
    ["Manufacturer using it in-house?", "No"],
    ["On FBR's Active Taxpayers List?", "Yes"],
  ] as [string, string][],
  lines: [
    { tax: "CD", label: "Customs duty", rate: "10%", amount: 50000, source: "Tariff, p.244" },
    { tax: "RD", label: "Regulatory duty", rate: "2%", amount: 10000, source: "SRO 1064(I)/2026, S.No 528" },
    { tax: "ACD", label: "Additional customs duty", rate: "0%", amount: 0, source: "No entry for this code" },
    { tax: "ST", label: "Sales tax", rate: "18%", amount: 100800, source: "Sales Tax Act s.3(1)(b)" },
    { tax: "VAT", label: "Value addition tax", rate: "3%", amount: 16800, source: "Twelfth Schedule, S.No 1" },
    { tax: "IT", label: "Income tax at import", rate: "6%", amount: 40656, source: "First Schedule Part II, S.No 3" },
  ],
  total: 218256,
  candidates: ["8507.6000", "8507.8000", "8507.5000"],
  unverified: ["Conditions of any concession are not checked", "Customs decides the final assessed value"],
};

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const smooth = (x: number) => x * x * (3 - 2 * x);
/** 0 before `a`, 1 after `b`, eased in between. */
export const ramp = (p: number, a: number, b: number) => smooth(clamp01((p - a) / (b - a)));
export const chapterAt = (p: number) => CHAPTERS.findLast((c) => p >= c.from) ?? CHAPTERS[0]!;

/** Rupee amounts with a fixed format, so the server and the browser print exactly the same text. */
export const fmtPKR = (n: number) => n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
