import { ContactSection, CoverageSection, FaqSection, ForFbrSection, WhySection } from "@/components/home/HomeSections";
import { ToolSections } from "@/components/home/ToolSections";
import { SmoothScroll } from "@/components/SmoothScroll";
import { Story } from "@/components/story/Story";

export default function Home() {
  return (
    <>
      <SmoothScroll />
      <Story />
      <div className="mx-auto grid max-w-6xl gap-20 px-4 pb-8 pt-16 sm:px-6 sm:pt-20">
        <WhySection />
        <ToolSections />
        <CoverageSection />
        <ForFbrSection />
        <FaqSection />
        <ContactSection />
      </div>
    </>
  );
}
