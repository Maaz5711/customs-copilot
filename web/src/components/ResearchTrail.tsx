import { BookOpen, Calculator, CheckCircle2, CircleHelp, Compass, Eye, FileText, RefreshCw, Scale, Search, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";

type Step = { key: string; Icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>; title: string; detail?: string; tone?: "ok" | "warn" };

const fmtHead = (h: string) => `${h.slice(0, 2)}.${h.slice(2)}`;
const clean = (s: string) => s.replace(/\s+/g, " ").trim();

/** Turn the agent's own trace lines into plain-language steps. Unknown lines are left out, never guessed at. */
export function trailSteps(trace: string[] | undefined): Step[] {
  const out: Step[] = [];
  (trace ?? []).forEach((raw, i) => {
    const t = clean(raw);
    const key = `${i}-${t.slice(0, 24)}`;
    let m: RegExpMatchArray | null;
    if (t.startsWith("understand: facts extracted")) out.push({ key, Icon: Eye, title: "Read your description", detail: "Picked out the product, material, use and importer details you wrote." });
    else if ((m = t.match(/^search: (\d+) lines, (\d+) notes, (\d+) SRO excerpts, (\d+) rulings/)))
      out.push({ key, Icon: Search, title: "Searched the official tariff", detail: `${m[1]} candidate lines, ${m[2]} legal notes, ${m[4]} rulings found.${t.includes("(retry") ? " (second look after a check failed)" : ""}` });
    else if ((m = t.match(/^explore: search '(.+?)' ->/))) out.push({ key, Icon: Search, title: "Tried another wording", detail: `“${m[1]}”` });
    else if ((m = t.match(/^explore: browse '(\d{4})'/))) out.push({ key, Icon: Compass, title: `Browsed heading ${fmtHead(m[1] ?? "")}`, detail: "Read every line under it to find the right sub-heading." });
    else if ((m = t.match(/^explore: notes '(\d{2})'/))) out.push({ key, Icon: BookOpen, title: `Read the Chapter ${m[1]} legal notes`, detail: "Checked what the chapter includes and excludes." });
    else if ((m = t.match(/^explore: rulings '(.+?)'/))) out.push({ key, Icon: FileText, title: "Checked FBR rulings on similar goods", detail: `“${m[1]}”` });
    else if (/^explore: done/.test(t)) out.push({ key, Icon: CheckCircle2, title: "Decided it had looked in the right places" });
    else if ((m = t.match(/^classify: top (\d{4}\.\d{4}) confidence (\d+)(?:%| out of 100)/)))
      out.push({ key, Icon: Scale, title: `Chose the best line: ${m[1]}`, detail: `Applied the General Rules of Interpretation and the legal notes (${m[2]}% confident).`, tone: "ok" });
    else if (/^classify: .*-> retry/.test(t)) out.push({ key, Icon: RefreshCw, title: "Was not satisfied, searched again", tone: "warn" });
    else if (/^classify: .*asking/.test(t)) out.push({ key, Icon: CircleHelp, title: "Needed one more fact, asked you", tone: "warn" });
    else if (/^calculate: (computed|cannot_compute)/.test(t) || /^calculate: tool status (computed|cannot_compute)/.test(t))
      out.push({ key, Icon: Calculator, title: "Calculated the bill with exact arithmetic", detail: "Every rate comes from the dated legal store; the language model does no maths." });
    else if (/^verify: passed/.test(t)) out.push({ key, Icon: ShieldCheck, title: "A second, independent check agreed", detail: "Separate call: does the line fit the goods, do the notes agree, is every figure sourced.", tone: "ok" });
    else if (/^verify: failed/.test(t)) out.push({ key, Icon: RefreshCw, title: "The independent check disagreed, tried again", tone: "warn" });
  });
  return out;
}

export function ResearchTrail({ trace }: { trace?: string[] }) {
  const steps = trailSteps(trace);
  if (steps.length < 2) return null;
  return (
    <details data-reveal className="rounded-xl border border-line bg-surface p-4" open>
      <summary className="font-semibold">How the agent worked it out ({steps.length} steps)</summary>
      <ol className="trail mt-3">
        {steps.map(({ key, Icon, title, detail, tone }) => (
          <li key={key} data-reveal className="trail-item">
            <span className={`trail-dot ${tone === "ok" ? "trail-ok" : tone === "warn" ? "trail-warn" : ""}`}><Icon size={15} aria-hidden={true} /></span>
            <div>
              <p className="text-[15px] font-semibold leading-snug">{title}</p>
              {detail && <p className="mt-0.5 text-sm text-ink-2">{detail}</p>}
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}
