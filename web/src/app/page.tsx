import { FileCheck2, HelpCircle, CalendarClock } from "lucide-react";
import Link from "next/link";
import { Reveal } from "@/components/Reveal";
import { Tool } from "@/components/Tool";

const PROMISES = [
  { icon: FileCheck2, title: "A source for every figure", text: "Each rate and amount points to the tariff page or SRO clause it came from." },
  { icon: CalendarClock, title: "Rules as of the date you choose", text: "FY2025-26 and FY2026-27, with the notification that applied on that day." },
  { icon: HelpCircle, title: "It says “I'm not sure”", text: "When the evidence is thin it shows its top candidates instead of guessing a code or a rate." },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-6 sm:pt-14">
      <Reveal className="mb-10 grid gap-8 lg:grid-cols-[1.15fr_1fr] lg:items-end">
        <div>
          <p data-reveal className="mb-3 text-sm font-semibold uppercase tracking-wider text-gold">Pakistan customs · import duty and tax</p>
          <h1 data-reveal className="font-display text-4xl font-semibold leading-[1.1] sm:text-5xl">The right customs code, and the whole bill behind it.</h1>
          <p data-reveal className="mt-4 max-w-xl text-lg text-ink-2">
            Describe what you are importing. Customs Copilot asks the questions the tariff notes require, finds the tariff line, and works out customs duty, regulatory duty, additional duty, sales tax and income tax, with the source of each figure.
          </p>
        </div>
        <ul className="grid gap-3">
          {PROMISES.map(({ icon: Icon, title, text }) => (
            <li key={title} data-reveal className="flex gap-3 rounded-xl border border-line bg-surface p-4">
              <Icon size={22} className="mt-0.5 shrink-0 text-blue" aria-hidden="true" />
              <div><p className="font-semibold">{title}</p><p className="text-[15px] text-ink-2">{text}</p></div>
            </li>
          ))}
        </ul>
      </Reveal>

      <Tool />

      <section className="mt-16 grid gap-6 md:grid-cols-3" aria-labelledby="how">
        <h2 id="how" className="sr-only">How it works</h2>
        {[
          ["Describe", "Say what the goods are. If something important is missing, the agent asks, one clear question at a time."],
          ["Check", "It searches the tariff, the legal notes and past classification rulings, then has a second, separate check review its choice."],
          ["Calculate", "Duty and tax arithmetic is done by exact code, never by the AI, and every line shows where its rate comes from."],
        ].map(([t, p], i) => (
          <div key={t} className="rounded-xl border border-line bg-surface p-5">
            <p className="num font-display text-sm font-semibold text-gold">Step {i + 1}</p>
            <h3 className="mt-1 font-display text-xl font-semibold">{t}</h3>
            <p className="mt-1.5 text-ink-2">{p}</p>
          </div>
        ))}
      </section>
      <p className="mt-8 text-center text-sm text-ink-2">How accurate is it? <Link href="/method#accuracy" className="font-semibold text-blue underline-offset-2 hover:underline">See the measured numbers and their limits.</Link></p>
    </div>
  );
}
