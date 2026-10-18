import { noteText, pkr } from "@/lib/api";
import type { BillLine, Totals } from "@/lib/types";

function rateText(l: BillLine): string {
  const r = l.rate;
  if (!r) return "–";
  if (r.kind === "percent" && r.pct !== undefined) return `${Number(r.pct)}%`;
  if (r.amount_pkr) return `PKR ${pkr(r.amount_pkr)} / ${r.unit ?? "unit"}`;
  return "–";
}

export function TotalsSummary({ totals }: { totals: Totals }) {
  const parts: [string, string][] = [
    ["Customs duties", totals.customs_duties],
    ["Excise", totals.federal_excise_duty],
    ["Sales tax", totals.sales_tax],
    ["Income tax", totals.income_tax],
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)]">
      <div data-reveal className="rounded-xl bg-brand p-5 text-on-brand">
        <p className="text-sm opacity-80">Total payable at import</p>
        <p className="num mt-1 font-display text-3xl font-semibold sm:text-4xl">PKR {pkr(totals.total_payable_pkr)}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3">
        {parts.map(([k, v]) => (
          <div key={k} data-reveal className="rounded-xl border border-line bg-surface-2 px-4 py-3">
            <dt className="text-sm text-ink-2">{k}</dt>
            <dd className="num font-semibold">PKR {pkr(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function BillTable({ lines }: { lines: BillLine[] }) {
  if (!lines.length) return null;
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[640px] border-collapse text-left text-[15px]">
        <caption className="sr-only">Itemised duty and tax bill with the source of each line</caption>
        <thead className="bg-surface-2 text-sm text-ink-2">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-semibold">Charge</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Rate</th>
            <th scope="col" className="px-4 py-2.5 text-right font-semibold">Charged on (PKR)</th>
            <th scope="col" className="px-4 py-2.5 text-right font-semibold">Amount (PKR)</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Source</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={`${l.tax}-${i}`} className="border-t border-line align-top">
              <th scope="row" className="px-4 py-3 font-semibold">
                {l.label}
                <span className="ml-2 text-xs font-normal text-ink-2">{l.tax}</span>
                {l.included_in_total === false && <span className="ml-2 text-xs font-normal text-warn">not in total</span>}
              </th>
              <td className="num px-4 py-3">{rateText(l)}</td>
              <td className="num px-4 py-3 text-right">{pkr(l.base_pkr)}</td>
              <td className="num px-4 py-3 text-right font-semibold">{pkr(l.amount_pkr)}</td>
              <td className="px-4 py-3 text-sm">
                <details>
                  <summary className="text-blue underline-offset-2 hover:underline">{l.clause ?? l.instrument ?? "Source"}</summary>
                  <div className="mt-1.5 space-y-0.5 text-ink-2">
                    {l.instrument && <p>{l.instrument}</p>}
                    {l.source_file && <p className="break-all">{l.source_file}{l.page ? `, page ${l.page}` : ""}</p>}
                    {l.valid_from && <p>Valid {l.valid_from} to {l.valid_to === "9999-12-31" ? "open end" : l.valid_to}</p>}
                    {l.status === "needs_review" && <p className="text-warn">This source row is marked for review.</p>}
                    {l.flags?.map((f, k) => <p key={k} className="text-warn">{noteText(f)}</p>)}
                  </div>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
