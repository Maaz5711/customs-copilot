import type { Metadata } from "next";
import { Reveal } from "@/components/Reveal";

export const metadata: Metadata = { title: "How it works", description: "How Customs Copilot finds a tariff code and calculates the bill, what it rests on, how accurate it is, and what it does not do." };

const ROWS: [string, string, string][] = [
  ["Right 4-digit heading, first answer", "72.5%", "960 real cleared lines"],
  ["Right 8-digit tariff line, first answer", "43.6%", "960 real cleared lines"],
  ["Right 8-digit line among its top 3", "56.6%", "960 real cleared lines"],
  ["Right 8-digit line when it commits to an answer", "62%", "407 of those lines"],
  ["Right 8-digit line, public classification rulings", "54%", "70 cases, 33 chapters"],
  ["Duty bill matches what Customs charged on every tax", "88%", "770 plain-rate lines"],
  ["China FTA customs duty matches what Customs charged", "95.8%", "5,491 lines"],
];

export default function Method() {
  return (
    <Reveal className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <h1 data-reveal className="font-display text-4xl font-semibold">How it works</h1>
      <p data-reveal className="mt-3 text-lg text-ink-2">What the tool does, what it rests on, and how often it is right. Measured on 18 October 2026.</p>

      <section data-reveal className="mt-10">
        <h2 className="font-display text-2xl font-semibold">How an answer is made</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-6 text-ink-2">
          <li>You describe the goods and choose the date the rules should apply.</li>
          <li>The agent searches the tariff, the legal notes and past classification rulings, and asks you the questions the notes make necessary (material, use, new or used, power).</li>
          <li>It proposes tariff lines. A separate check reviews the choice against the legal notes before anything is shown as an answer.</li>
          <li>Duties and taxes are calculated by exact code. Every line carries the tariff page or notification it came from, and the dated rule that applied.</li>
          <li>If the evidence stays thin after two retries, it says it is not sure and shows its top three candidates.</li>
        </ol>
      </section>

      <section data-reveal className="mt-10">
        <h2 className="font-display text-2xl font-semibold">What it rests on</h2>
        <p className="mt-3 text-ink-2">Public FBR documents for FY2025-26 and FY2026-27: the Pakistan Customs Tariff, the Customs Act, the regulatory and additional duty notifications, the Fifth Schedule, the China FTA notification as amended in 2022, the Sales Tax Act and its schedules, the Income Tax Ordinance, the Finance Acts, and the Classification Committee rulings. Scanned notifications were read by AI and then checked by rules (row counts, ranges, cross-checks). Nothing is written from memory.</p>
      </section>

      <section id="accuracy" data-reveal className="mt-10 scroll-mt-20">
        <h2 className="font-display text-2xl font-semibold">How accurate is it?</h2>
        <div className="mt-4 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[480px] border-collapse text-left text-[15px]">
            <thead className="bg-surface-2 text-sm text-ink-2"><tr><th scope="col" className="px-4 py-2.5">Measure</th><th scope="col" className="px-4 py-2.5 text-right">Result</th><th scope="col" className="px-4 py-2.5">Tested on</th></tr></thead>
            <tbody>
              {ROWS.map(([a, b, c]) => (
                <tr key={a} className="border-t border-line"><th scope="row" className="px-4 py-3 font-normal">{a}</th><td className="num px-4 py-3 text-right font-semibold">{b}</td><td className="px-4 py-3 text-ink-2">{c}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 space-y-3 text-ink-2">
          <p><strong className="text-ink">Read these as lower bounds.</strong> The real cleared lines are one month of Chapter 85 (electrical goods) from one source, and the code an importer declared is not always the legally correct one: importers disagree with each other on about 28% of identical descriptions.</p>
          <p>The public rulings are contested cases, so they are harder than everyday goods. Both sets are small, and the intervals are wide. Published research on this task reports similar results: the best AI agents reach about 47% at the full national code, where human experts with the full product page and a rulings database reach about 95%.</p>
          <p>When a description is too short to decide, the agent asks a question. In our tests it is right far more often when it answers than when it has to ask, which is the behaviour we want from a tool you rely on for money.</p>
        </div>
      </section>

      <section data-reveal className="mt-10">
        <h2 className="font-display text-2xl font-semibold">What it does not do</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-6 text-ink-2">
          <li>It is not an FBR service and gives no legal or customs advice. Customs decides the code and the value.</li>
          <li>It does not apply a concession you have not claimed, and it cannot check certificates, approvals or origin proof. It shows what a concession would save and what you must prove.</li>
          <li>It covers FY2025-26 and FY2026-27 only, and the China FTA among trade agreements. Valuation disputes, used-vehicle valuation and filing a declaration are out of scope.</li>
          <li>A few things are flagged as open questions in the answer instead of being guessed, for example some additional customs duty rates on automotive electrical parts.</li>
        </ul>
      </section>
    </Reveal>
  );
}
