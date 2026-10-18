import type { Metadata } from "next";
import { Reveal } from "@/components/Reveal";

export const metadata: Metadata = { title: "Privacy and security", description: "What Customs Copilot does with what you type, what it stores, and how the service is protected." };

const Item = ({ t, children }: { t: string; children: React.ReactNode }) => (
  <li data-reveal className="rounded-xl border border-line bg-surface p-4"><p className="font-semibold">{t}</p><p className="mt-1 text-[15px] text-ink-2">{children}</p></li>
);

export default function Security() {
  return (
    <Reveal className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <h1 data-reveal className="font-display text-4xl font-semibold">Privacy and security</h1>
      <p data-reveal className="mt-3 text-lg text-ink-2">What happens to what you type, and how the service is protected.</p>

      <h2 data-reveal className="mt-10 font-display text-2xl font-semibold">Your data</h2>
      <ul className="mt-3 grid gap-3">
        <Item t="What you type is read by an AI provider">The product description and your answers are sent to the AI service that reads them (currently DeepSeek). Do not enter names, phone numbers, company names or other personal data.</Item>
        <Item t="Conversations are kept in memory for one hour">They are not written to disk, and a restart forgets them. We do not keep a log of what you type, and error logs record only the type of error.</Item>
        <Item t="No accounts, no tracking">No sign-up, no advertising or analytics scripts, no third-party fonts or images. Your theme choice is stored in your own browser only.</Item>
        <Item t="Feedback is optional and consent-based">If you tick the box we store the code you believe is right and a short note. Without it, only “not helpful” is counted and nothing else is kept.</Item>
      </ul>

      <h2 data-reveal className="mt-10 font-display text-2xl font-semibold">How the service is protected</h2>
      <ul className="mt-3 grid gap-3">
        <Item t="Strict browser rules">A per-request Content-Security-Policy allows only our own scripts and styles, nothing loads from another site, and the page cannot be framed by another site.</Item>
        <Item t="Everything you send is validated">Every field has a type and a length limit, unknown fields are refused, and error messages never repeat what you typed.</Item>
        <Item t="Abuse limits">Requests are rate-limited per visitor, request size is capped, and the AI budget has a ceiling so a flood cannot run up costs.</Item>
        <Item t="Secrets stay on the server">API keys never reach your browser. Dependencies are pinned and checked for known vulnerabilities.</Item>
      </ul>
      <p data-reveal className="mt-8 text-ink-2">No online service can honestly promise it can never be breached. We design for the smallest possible exposure: we hold very little, so there is very little to lose.</p>
    </Reveal>
  );
}
