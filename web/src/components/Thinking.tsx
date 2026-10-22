import { BrainCircuit } from "lucide-react";
import { trailSteps } from "./ResearchTrail";

/** What the agent is most likely doing next, from the last step it reported. Shown as the "now" line, so the page never looks frozen. */
function nextPhase(trace: string[]): string {
  const last = trace[trace.length - 1] ?? "";
  if (!last) return "Reading your description";
  if (last.startsWith("understand")) return "Searching the official tariff and the legal notes";
  if (last.startsWith("search")) return "Researching: trying other wordings and checking notes and rulings";
  if (last.startsWith("explore")) return "Weighing the candidate lines against the legal notes";
  if (last.startsWith("classify")) return "Calculating the bill with exact arithmetic";
  if (last.startsWith("calculate")) return "Double-checking the answer with an independent review";
  if (last.startsWith("verify")) return "Writing the answer with its sources";
  return "Thinking it through";
}

/** The agent at work: an animated thinking icon, a running timer, the steps it has really taken so far, and what it is doing now. */
export function Thinking({ trace, secs }: { trace: string[]; secs: number }) {
  const steps = trailSteps(trace);
  return (
    <div role="status" aria-live="polite" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-3">
        <span className="think-icon" aria-hidden="true"><BrainCircuit size={24} /></span>
        <div>
          <p className="font-display text-lg font-semibold">Thinking<span className="think-dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></p>
          <p className="text-sm text-ink-2"><span className="num">{secs}s</span> · the agent reads, researches the tariff and double-checks. A new question can take up to a minute.</p>
        </div>
      </div>
      {steps.length > 0 && (
        <ol className="trail mt-4" aria-label="Steps taken so far">
          {steps.map(({ key, Icon, title, detail, tone }) => (
            <li key={key} className="trail-item think-step">
              <span className={`trail-dot ${tone === "ok" ? "trail-ok" : tone === "warn" ? "trail-warn" : ""}`}><Icon size={15} aria-hidden={true} /></span>
              <div>
                <p className="text-[15px] font-semibold leading-snug">{title}</p>
                {detail && <p className="mt-0.5 text-sm text-ink-2">{detail}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
      <p className="think-now mt-4 flex items-center gap-2 text-[15px] text-ink-2"><span className="think-pip" aria-hidden="true" />{nextPhase(trace)}…</p>
    </div>
  );
}
