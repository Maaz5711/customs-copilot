"use client";
import { ArrowUp } from "lucide-react";
import { useEffect, useState } from "react";
import { glideTo } from "./SmoothScroll";

// A small round button that appears after the first screen and glides back to the top.
export function BackToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(window.scrollY > window.innerHeight * 1.5);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <button type="button" className="to-top" data-show={show} aria-label="Back to top" tabIndex={show ? 0 : -1} onClick={() => glideTo(0)}>
      <ArrowUp size={20} aria-hidden="true" />
    </button>
  );
}
