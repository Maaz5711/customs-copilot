"use client";
import { useId, useState } from "react";
import { api } from "@/lib/api";
import { Button, Field, TextInput } from "./ui";

// "Was this right?" Nothing free-text is sent or stored unless the visitor ticks the consent box. The thread id is only kept with consent too.
export function Feedback({ threadId, code }: { threadId?: string; code?: string | null }) {
  const id = useId();
  const [stage, setStage] = useState<"ask" | "form" | "sent" | "error">("ask");
  const [rightCode, setRightCode] = useState("");
  const [note, setNote] = useState("");
  const [consent, setConsent] = useState(false);

  const send = async (helpful: boolean) => {
    try {
      const codeOk = /^\d{8}$/.test(rightCode.replace(/\D/g, "")) ? rightCode.replace(/\D/g, "") : undefined;
      await api.feedback({ helpful, thread_id: consent ? threadId : undefined, code: consent ? codeOk ?? (helpful ? code ?? undefined : undefined) : undefined, note: consent && note ? note : undefined, consent_to_store_note: consent });
      setStage("sent");
    } catch {
      setStage("error");
    }
  };

  if (stage === "sent") return <p className="text-ink-2" role="status">Thank you. Your feedback helps us improve.</p>;
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-4">
      {stage === "ask" || stage === "error" ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-semibold">Was this the right code?</p>
          <Button variant="secondary" onClick={() => send(true)}>Yes</Button>
          <Button variant="secondary" onClick={() => setStage("form")}>No or not sure</Button>
          {stage === "error" && <p className="text-bad" role="alert">Could not send. Please try again.</p>}
        </div>
      ) : (
        <div className="grid gap-3 sm:max-w-lg">
          <Field label="The code you believe is right (optional, 8 digits)" htmlFor={`${id}-c`}>
            <TextInput id={`${id}-c`} inputMode="numeric" maxLength={11} value={rightCode} onChange={(e) => setRightCode(e.target.value)} placeholder="e.g. 8471.3010" />
          </Field>
          <Field label="Anything we should know? (optional)" htmlFor={`${id}-n`} hint="Do not include names, phone numbers or company details.">
            <TextInput id={`${id}-n`} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 size-4" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>Store my code and note to help improve the tool. Without this box ticked, only “not helpful” is counted and nothing else is kept.</span>
          </label>
          <div className="flex gap-3">
            <Button onClick={() => send(false)}>Send feedback</Button>
            <Button variant="ghost" onClick={() => setStage("ask")}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
