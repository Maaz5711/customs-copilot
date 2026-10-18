import { AskHero } from "@/components/home/AskHero";
import { ContactSection, CoverageSection, FaqSection, ForFbrSection, WhySection } from "@/components/home/HomeSections";
import { ToolSections } from "@/components/home/ToolSections";
import { ToolsProvider } from "@/components/home/ToolsContext";
import { SmoothScroll } from "@/components/SmoothScroll";
import { Story } from "@/components/story/Story";

// Search first (an answer in seconds), then the scroll story as "How it works", then the context and the other tools.
export default function Home() {
  return (
    <ToolsProvider>
      <SmoothScroll />
      <AskHero />
      <div id="how" className="scroll-mt-24 border-t border-line bg-[var(--paper-soft)]">
        <div className="mx-auto max-w-4xl px-4 pb-6 pt-14 text-center sm:px-6">
          <p className="hud-label text-gold">How it works</p>
          <h2 className="mt-1 font-display text-3xl font-semibold leading-tight sm:text-4xl">From the ship to the green gate, step by step</h2>
          <p className="mx-auto mt-3 max-w-2xl text-[17px] text-ink-2">Scroll to watch how one real example, a power bank worth PKR 500,000, gets its code, its bill and its sources.</p>
        </div>
      </div>
      <Story />
      <div className="mx-auto grid max-w-6xl gap-20 px-4 pb-8 pt-16 sm:px-6 sm:pt-20">
        <WhySection />
        <ToolSections />
        <CoverageSection />
        <ForFbrSection />
        <FaqSection />
        <ContactSection />
      </div>
    </ToolsProvider>
  );
}
