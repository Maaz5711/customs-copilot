import { BadgeCheck, Calculator, CalendarClock, ExternalLink, FileSearch, HelpCircle, Mail, ScrollText, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

// The context sections of the home page: why it is different, what it covers, the note to FBR and Pakistan Customs, FAQ and contact.
// Every claim here is backed by the code or by measured results (docs/eval_versions.md, docs/gd_findings.md, /method).

// Paste the LinkedIn profile address here; the button appears only when it is set.
const DEVELOPER = { name: "Maaz Ahmed", email: "maazahmad3838@gmail.com", github: "https://github.com/Maaz5711", linkedin: "" };

function SectionHead({ id, kicker, title, lead }: { id: string; kicker: string; title: string; lead?: ReactNode }) {
  return (
    <div className="max-w-3xl">
      <p className="hud-label text-gold">{kicker}</p>
      <h2 id={id} className="mt-1 font-display text-3xl font-semibold leading-tight sm:text-4xl">{title}</h2>
      {lead && <p className="mt-3 text-[17px] text-ink-2">{lead}</p>}
    </div>
  );
}

const PILLARS: [ReactNode, string, ReactNode][] = [
  [<ScrollText key="i" size={20} />, "Every figure cites its source", "Each rate points to the page of the Customs Tariff, the SRO number and serial, or the section of the Act it comes from. You can check every line yourself."],
  [<Calculator key="i" size={20} />, "The whole bill, not just customs duty", "Customs duty, regulatory duty, additional customs duty, sales tax, further tax, 3% value addition tax, income tax (filer and non-filer) and FED, in one bill. Where a rate cannot be worked out yet, it says so instead of guessing."],
  [<BadgeCheck key="i" size={20} />, "Exact arithmetic, never the AI", "The AI only reads and asks questions. Every rupee is computed by exact code from the dated legal store, so the same inputs always give the same bill."],
  [<CalendarClock key="i" size={20} />, "Rules by date", "Choose the date your goods are assessed. Rates change with each Finance Act and SRO; the tool applies the rules in force on that date for FY2025-26 and FY2026-27."],
  [<HelpCircle key="i" size={20} />, "Says “not sure” instead of guessing", "When the evidence is thin it asks you a question or shows its top three codes with their reasons. It never invents a code, a rate or an SRO number."],
  [<FileSearch key="i" size={20} />, "Checked against real declarations", <>On 770 real plain-rate import lines, the bill matched what Customs charged on every tax in 88% of them. <Link href="/method#accuracy" className="font-semibold text-blue underline-offset-2 hover:underline">See all measured results and their limits.</Link></>],
];

const COMPARE: [string, string, string][] = [
  ["Find the code from a plain description", "Keyword search: you must already know the words the tariff uses", "Asks the questions the tariff needs, then gives the code or its top 3"],
  ["Taxes in the bill", "Often customs duty only, or a partial set", "All import charges, including further tax, 3% value addition tax and FED"],
  ["Source for each figure", "Rarely shown", "Tariff page, SRO serial or Act section on every line"],
  ["Which rules", "Usually today's only", "Any date in FY2025-26 and FY2026-27"],
  ["When it is unsure", "Always gives an answer", "Says so, and shows the alternatives"],
];

const COVERS: [string, string][] = [
  ["Customs duty (CD)", "Pakistan Customs Tariff (First Schedule to the Customs Act, 1969), FY2025-26 and FY2026-27"],
  ["Regulatory duty (RD)", "SRO 1064(I)/2026 (FY2026-27) and SRO 1152(I)/2025 (FY2025-26)"],
  ["Additional customs duty (ACD)", "SRO 1063(I)/2026 (FY2026-27) and SRO 1151(I)/2025 (FY2025-26)"],
  ["Sales tax and further tax", "Sales Tax Act, 1990"],
  ["Value addition tax (3%)", "Twelfth Schedule to the Sales Tax Act, 1990"],
  ["Income tax at import", "Income Tax Ordinance, 2001 (First Schedule Part II; non-filer rule in the Tenth Schedule)"],
  ["Federal excise duty (FED)", "Federal Excise Act, 2005 (First Schedule)"],
  ["Concessions, offered and never applied silently", "Fifth Schedule to the Customs Act; China–Pakistan FTA (SRO 1181(I)/2022 table)"],
];

const FAQ: [string, ReactNode][] = [
  ["Is this an official FBR or Pakistan Customs tool?", "No. Customs Copilot is an independent project. It is built to assist the work of FBR, Pakistan Customs, clearing agents and importers, using only FBR's published documents, but it is not an FBR service and is not endorsed by FBR. Always confirm with Pakistan Customs or a licensed customs agent before you import."],
  ["Where do the rates come from?", "From FBR's published documents: the Customs Tariff for each fiscal year, the regulatory and additional customs duty SROs, the Sales Tax Act, the Income Tax Ordinance, the Federal Excise Act, the Fifth Schedule and the China FTA tables. Every line of a bill names the page, serial or section it came from."],
  ["How accurate is it?", <>The duty arithmetic matched what Customs charged on every tax for 88% of 770 real plain-rate lines. Finding the exact 8-digit code from a description is harder: it was right first time on 43.6% of 960 real cleared lines and on the right 4-digit heading 72.5% of the time, which is why it asks questions and shows its top three. <Link href="/method#accuracy" className="font-semibold text-blue underline-offset-2 hover:underline">Full results and limits.</Link></>],
  ["Which goods can it not calculate yet?", "A few cases have special tax tables or legal questions still open, for example mobile phones, sugar, Chapter 99 and some vehicles (electric cars, CKD kits). For these it tells you it cannot compute the figure rather than guessing."],
  ["Which years are covered?", "FY2025-26 and FY2026-27. Pick any date in that range and the tool applies the rules in force on that date."],
  ["What happens to what I type?", <>Conversations are held in memory for at most an hour and then deleted. There are no accounts and no cookies. The description you type is sent to the AI provider to read it, so do not enter personal or confidential details. <Link href="/security" className="font-semibold text-blue underline-offset-2 hover:underline">Privacy and security.</Link></>],
  ["Is it free?", "Yes. It is a free project."],
  ["Can FBR, Pakistan Customs or a clearing agency use it?", "Yes, that is the aim. If you would like to evaluate it, test it on your own cases or discuss an official version, please get in touch with the developer below."],
];

export function WhySection() {
  return (
    <section aria-labelledby="why-h" id="why" className="scroll-mt-24">
      <SectionHead id="why-h" kicker="Why Customs Copilot" title="The right code and the full bill, with proof for every rupee."
        lead="Most online helpers stop at a keyword search or a customs duty estimate. Customs Copilot works the way a careful clearing agent does: it checks the goods, finds the tariff line and builds the complete bill from FBR's own documents." />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PILLARS.map(([icon, t, p]) => (
          <div key={t} className="rounded-xl border border-line bg-surface p-5">
            <span className="inline-flex size-10 items-center justify-center rounded-xl bg-gold-soft text-gold" aria-hidden="true">{icon}</span>
            <h3 className="mt-3 font-display text-lg font-semibold">{t}</h3>
            <p className="mt-1.5 text-[15px] text-ink-2">{p}</p>
          </div>
        ))}
      </div>
      <div className="mt-8 overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[40rem] text-left text-[15px]">
          <caption className="sr-only">Customs Copilot compared with typical free lookup tools</caption>
          <thead className="bg-surface-2 text-sm">
            <tr><th scope="col" className="px-4 py-3 font-semibold"> </th><th scope="col" className="px-4 py-3 font-semibold text-ink-2">Typical free lookup tools</th><th scope="col" className="px-4 py-3 font-semibold">Customs Copilot</th></tr>
          </thead>
          <tbody>
            {COMPARE.map(([row, them, us]) => (
              <tr key={row} className="border-t border-line align-top">
                <th scope="row" className="px-4 py-3 font-semibold">{row}</th>
                <td className="px-4 py-3 text-ink-2">{them}</td>
                <td className="px-4 py-3">{us}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-2">Based on the public pages of free Pakistani code-lookup tools, checked 18 Oct 2026.</p>
    </section>
  );
}

export function CoverageSection() {
  return (
    <section aria-labelledby="cover-h" id="coverage" className="scroll-mt-24">
      <SectionHead id="cover-h" kicker="What it covers" title="Every import charge, from the document that sets it." />
      <dl className="mt-8 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
        {COVERS.map(([k, v]) => (
          <div key={k} className="bg-surface p-4">
            <dt className="font-semibold">{k}</dt>
            <dd className="mt-0.5 text-[15px] text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function ForFbrSection() {
  return (
    <section aria-labelledby="fbr-h" id="fbr" className="scroll-mt-24 rounded-2xl border border-line bg-surface p-6 sm:p-8">
      <div className="flex flex-wrap items-start gap-4">
        <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-xl bg-ok-soft text-ok" aria-hidden="true"><ShieldCheck size={24} /></span>
        <div className="min-w-0 flex-1">
          <p className="hud-label">Independent · not an FBR service</p>
          <h2 id="fbr-h" className="mt-1 font-display text-2xl font-semibold sm:text-3xl">Built to assist FBR and Pakistan Customs</h2>
          <p className="mt-3 max-w-3xl text-ink-2">
            Customs Copilot is designed so that it could sit beside FBR&rsquo;s own services: it uses only FBR&rsquo;s published documents, cites them line by line,
            keeps almost no user data, does the arithmetic exactly, and publishes its measured accuracy openly. It is an independent project and is not
            affiliated with or endorsed by FBR. Officials who would like to evaluate it are welcome to get in touch.
          </p>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-line bg-surface-2/60 p-4">
              <p className="hud-label">Checked against FBR&rsquo;s own calculator</p>
              <p className="num mt-1 font-display text-3xl font-semibold">30 of 33</p>
              <p className="mt-1 text-sm text-ink-2">FY2026-27 codes where customs duty, regulatory duty, additional customs duty and sales tax matched FBR&rsquo;s public WeBOC duty calculator to the rupee (16 Oct 2026). The three differences are vehicle parts, still under review.</p>
            </div>
            <div className="rounded-xl border border-line bg-surface-2/60 p-4 md:col-span-2">
              <p className="hud-label">Where it fits in the clearance process</p>
              <ol className="mt-2 grid gap-2 sm:grid-cols-3">
                {[["1", "Prepare", "Find the PCT code and the full bill here, with the source of every rate."], ["2", "File", "Lodge the Goods Declaration through WeBOC or the Pakistan Single Window, as usual."], ["3", "Assess", "Pakistan Customs assesses and clears the goods. Their decision is final."]].map(([n, t, d]) => (
                  <li key={n} className="rounded-lg border border-line bg-surface p-3">
                    <p className="flex items-center gap-2 font-semibold"><span className="num inline-flex size-6 items-center justify-center rounded-full bg-brand text-xs text-on-brand">{n}</span>{t}</p>
                    <p className="mt-1 text-sm text-ink-2">{d}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <p className="mt-4 text-sm text-ink-2">Official tariff, SROs and Acts: <a href="https://www.fbr.gov.pk" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-blue underline-offset-2 hover:underline">fbr.gov.pk <ExternalLink size={13} aria-hidden="true" /></a></p>
          <div className="mt-5 flex flex-wrap gap-3">
            <a href="#contact" className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand hover:opacity-90">Contact the developer</a>
            <Link href="/method" className="inline-flex min-h-11 items-center rounded-lg border border-line px-5 py-2 text-[15px] font-semibold hover:bg-surface-2">How it works and how it was tested</Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export function FaqSection() {
  return (
    <section aria-labelledby="faq-h" id="faq" className="scroll-mt-24">
      <SectionHead id="faq-h" kicker="FAQ" title="Questions people ask" />
      <div className="mt-6 divide-y divide-line rounded-xl border border-line bg-surface">
        {FAQ.map(([q, a]) => (
          <details key={q} className="group px-5 py-1">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 py-3 font-semibold">
              {q}
              <span className="text-xl text-ink-2 transition-transform group-open:rotate-45" aria-hidden="true">+</span>
            </summary>
            <p className="pb-4 text-[15px] text-ink-2">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function ContactSection() {
  return (
    <section aria-labelledby="contact-h" id="contact" className="scroll-mt-24">
      <SectionHead id="contact-h" kicker="Contact" title="Talk to the developer"
        lead="Feedback, real cases where the tool got it wrong, or interest from FBR, Pakistan Customs, clearing agents and importers: all welcome." />
      <div className="mt-6 flex flex-wrap items-center gap-5 rounded-xl border border-line bg-surface p-5 sm:p-6">
        <span className="inline-flex size-14 items-center justify-center rounded-full bg-brand font-display text-xl font-semibold text-on-brand" aria-hidden="true">MA</span>
        <div className="min-w-0 flex-1">
          <p className="font-display text-xl font-semibold">{DEVELOPER.name}</p>
          <p className="text-ink-2">Developer of Customs Copilot · computer science student</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={`mailto:${DEVELOPER.email}?subject=Customs%20Copilot`} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand px-5 py-2 text-[15px] font-semibold text-on-brand hover:opacity-90">
            <Mail size={17} aria-hidden="true" /> {DEVELOPER.email}
          </a>
          <a href={DEVELOPER.github} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line px-4 py-2 text-[15px] font-semibold hover:bg-surface-2">
            GitHub <ExternalLink size={14} aria-hidden="true" />
          </a>
          {DEVELOPER.linkedin && (
            <a href={DEVELOPER.linkedin} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line px-4 py-2 text-[15px] font-semibold hover:bg-surface-2">
              LinkedIn <ExternalLink size={14} aria-hidden="true" />
            </a>
          )}
        </div>
      </div>
    </section>
  );
}
