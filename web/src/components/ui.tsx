import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

export function Button({ variant = "primary", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const base = "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-[15px] font-semibold transition-colors duration-200 select-none";
  const v = {
    primary: "bg-brand text-on-brand hover:opacity-90",
    secondary: "border border-line bg-surface text-ink hover:bg-surface-2",
    ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  }[variant];
  return <button type="button" className={cx(base, v, className)} {...p} />;
}

export function Card({ className, children, ...p }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("rounded-xl border border-line bg-surface p-5 sm:p-6", className)} {...p}>
      {children}
    </div>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "bad" | "gold"; children: ReactNode }) {
  const t = { neutral: "bg-surface-2 text-ink-2", ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad", gold: "bg-gold-soft text-gold" }[tone];
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", t)}>{children}</span>;
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-semibold text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="text-[13px] text-ink-2">{hint}</p>}
    </div>
  );
}

export const inputClass =
  "min-h-11 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[16px] text-ink placeholder:text-ink-2/70 focus:border-blue";

export function TextInput(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={inputClass} {...p} />;
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "bad" | "ok"; title?: string; children: ReactNode }) {
  const t = { info: "border-line bg-surface-2", warn: "border-warn/40 bg-warn-soft", bad: "border-bad/40 bg-bad-soft", ok: "border-ok/40 bg-ok-soft" }[tone];
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cx("rounded-lg border px-4 py-3 text-[15px]", t)}>
      {title && <p className="font-semibold">{title}</p>}
      <div className={title ? "mt-0.5" : ""}>{children}</div>
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 text-ink-2" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
