"use client";
import { useEffect, useState } from "react";
import { api, pkr } from "@/lib/api";
import type { BillLine, Candidate } from "@/lib/types";

// "What if Customs classified it differently?" For each alternative code the agent considered, the exact calculator works out the customs duties
// (CD + RD + ACD) on the same value and date, and shows the difference from the chosen line. Sales tax and income tax are left out because they also
// depend on importer facts; the customs duties do not.

const CUSTOMS = new Set(["CD", "RD", "ACD"]);
const fmtCode = (c: string) => (c.length === 8 ? `${c.slice(0, 4)}.${c.slice(4)}` : c);
const sumCustoms = (lines: BillLine[] = []) => lines.filter((l) => CUSTOMS.has(l.tax)).reduce((s, l) => s + Number(l.amount_pkr || 0), 0);
const rateOf = (lines: BillLine[] = [], tax: string) => lines.find((l) => l.tax === tax)?.rate?.pct;

type Row = { code: string; description?: string; customs?: number; cd?: string; rd?: string; acd?: string; error?: boolean };

export function CandidateCompare({ chosen, lines, candidates, date }: { chosen: string; lines: BillLine[]; candidates: Candidate[]; date?: string }) {
  const value = Number(lines.find((l) => l.tax === "CD")?.base_pkr ?? 0);
  const base = sumCustoms(lines);
  const others = candidates.filter((c) => c.code !== chosen).slice(0, 3);
  const [rows, setRows] = useState<Row[] | null>(null);
  const key = `${chosen}|${value}|${date}|${others.map((c) => c.code).join(",")}`;

  useEffect(() => {
    if (!value || !others.length) return;
    let dead = false;
    Promise.all(others.map(async (c): Promise<Row> => {
      try {
        const r = await api.bill({ code: c.code, value_pkr: value, date, importer: {}, goods: {} });
        const ls = r.lines ?? [];
        if (!ls.some((l) => l.tax === "CD")) return { code: c.code, description: c.description, error: true };
        return { code: c.code, description: c.description, customs: sumCustoms(ls), cd: rateOf(ls, "CD"), rd: rateOf(ls, "RD"), acd: rateOf(ls, "ACD") };
      } catch {
        return { code: c.code, description: c.description, error: true };
      }
    })).then((r) => { if (!dead) setRows(r); });
    return () => { dead = true; };
  }, [key]);

  if (!value || !others.length) return null;
  return (
    <section aria-label="Duty if classified under another code" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <h3 className="font-display text-lg font-semibold">If Customs classified it differently</h3>
      <p className="mt-1 text-sm text-ink-2">Customs duties (CD + RD + ACD) on the same value, PKR {pkr(value)}, for the other codes I considered. Chosen line {fmtCode(chosen)}: PKR {pkr(base)}.</p>
      {!rows && <p className="mt-3 text-sm text-ink-2">Working out the alternatives…</p>}
      {rows && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-[15px]">
            <thead className="text-sm text-ink-2"><tr><th scope="col" className="py-1.5 pr-3 font-semibold">Code</th><th scope="col" className="py-1.5 pr-3 font-semibold">CD / RD / ACD</th><th scope="col" className="py-1.5 pr-3 text-right font-semibold">Customs duties</th><th scope="col" className="py-1.5 text-right font-semibold">Difference</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const diff = r.customs === undefined ? undefined : r.customs - base;
                return (
                  <tr key={r.code} className="border-t border-line align-top">
                    <th scope="row" className="py-2 pr-3 font-normal"><span className="num font-semibold">{fmtCode(r.code)}</span>{r.description && <span className="block max-w-xs truncate text-xs text-ink-2">{r.description}</span>}</th>
                    <td className="num py-2 pr-3 text-ink-2">{r.error ? "—" : `${r.cd ?? "0"}% / ${r.rd ?? "0"}% / ${r.acd ?? "0"}%`}</td>
                    <td className="num py-2 pr-3 text-right">{r.error ? "could not compute" : `PKR ${pkr(r.customs!)}`}</td>
                    <td className={`num py-2 text-right font-semibold ${diff === undefined || diff === 0 ? "text-ink-2" : diff > 0 ? "text-bad" : "text-ok"}`}>{diff === undefined ? "—" : diff === 0 ? "same" : `${diff > 0 ? "+" : "−"}PKR ${pkr(Math.abs(diff))}`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-ink-2">Exact calculation from the same dated rules. Sales tax and income tax change too, but they also depend on your registration and filer status.</p>
    </section>
  );
}
