import Link from "next/link";
import { SmoothScroll } from "@/components/SmoothScroll";
import { Story } from "@/components/story/Story";
import { Tool } from "@/components/Tool";

export default function Home() {
  return (
    <>
      <SmoothScroll />
      <Story />
      <div id="tool" className="mx-auto max-w-6xl scroll-mt-6 px-4 pb-8 pt-16 sm:px-6 sm:pt-20">
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
    </>
  );
}
