import type { Metadata, Viewport } from "next";
import { Lexend, Source_Sans_3 } from "next/font/google";
import { headers } from "next/headers";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { BackToTop } from "@/components/BackToTop";
import { ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

// Fonts are downloaded once at build time and served from our own origin: visitors never contact Google.
const lexend = Lexend({ subsets: ["latin"], variable: "--font-lexend", display: "swap" });
const source = Source_Sans_3({ subsets: ["latin"], variable: "--font-source", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Customs Copilot · Pakistan Customs Duty Calculator", template: "%s · Customs Copilot" },
  description: "Pakistan customs duty calculator: find the right PCT code and see the full duty and tax bill (CD, RD, ACD, sales tax, income tax, FED), with the FBR source of every figure. Independent; not an FBR service.",
  robots: { index: true, follow: true },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f8fb" }, { media: "(prefers-color-scheme: dark)", color: "#0a1020" }] };

const THEME_SCRIPT = `try{var t=localStorage.getItem("cc-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" className={`${lexend.variable} ${source.variable}`} suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="site-header sticky top-0 z-40 border-b border-line bg-surface/85 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-2 px-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 whitespace-nowrap font-display text-[16px] font-semibold text-ink sm:gap-2.5 sm:text-[17px]">
              <span className="inline-flex size-8 items-center justify-center rounded-lg bg-brand text-on-brand"><ShieldCheck size={18} aria-hidden="true" /></span>
              <span className="flex flex-col leading-tight">
                Customs Copilot
                <span className="hidden font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-2 sm:block">Pakistan Customs Duty Calculator</span>
              </span>
            </Link>
            <nav aria-label="Main" className="flex items-center text-[14px] sm:gap-1 sm:text-[15px]">
              <Link href="/#describe" className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-ink-2 hover:bg-surface-2 hover:text-ink lg:inline-block">Tools</Link>
              <Link href="/#faq" className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-ink-2 hover:bg-surface-2 hover:text-ink lg:inline-block">FAQ</Link>
              <Link href="/#contact" className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-ink-2 hover:bg-surface-2 hover:text-ink md:inline-block">Contact</Link>
              <Link href="/method" className="whitespace-nowrap rounded-lg px-2 py-2 text-ink-2 hover:bg-surface-2 hover:text-ink sm:px-3">How it works</Link>
              <Link href="/security" className="whitespace-nowrap rounded-lg px-2 py-2 text-ink-2 hover:bg-surface-2 hover:text-ink sm:px-3">Privacy</Link>
              <ThemeToggle />
              <Link href="/#describe" className="ml-1 hidden min-h-10 items-center whitespace-nowrap rounded-lg bg-brand px-4 text-[14px] font-semibold text-on-brand hover:opacity-90 sm:inline-flex">Find my duty</Link>
            </nav>
          </div>
        </header>
        <main id="main">{children}</main>
        <BackToTop />
        <footer className="mt-20 border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-ink-2 sm:px-6">
            <p className="max-w-3xl">
              Independent project, built to assist FBR and Pakistan Customs. Customs Copilot is not an FBR service, is not endorsed by FBR, and gives no legal or customs advice.
              Check with Pakistan Customs or a licensed customs agent before you import. Rules covered: FY2025-26 and FY2026-27.
            </p>
            <p className="mt-2">Built from public FBR documents. <Link href="/method" className="underline">Sources and accuracy</Link> · <Link href="/security" className="underline">Privacy and security</Link> · <Link href="/#contact" className="underline">Contact</Link></p>
            <p className="mt-2">Designed and developed by <span className="font-semibold text-ink">Maaz Ahmed</span>.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
