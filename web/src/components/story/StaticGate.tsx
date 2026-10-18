// The same gate as a flat drawing. It is what people see when the 3D scene is not used: reduced motion, no WebGL, a low-power device, or before the
// scene has loaded. It uses the page's colour tokens, so it follows light and dark mode.
export function StaticGate({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 520 300" role="img" aria-label="A customs gate with a crate waiting inside it" className={className}>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <g className="stroke-blue" strokeWidth="1" opacity=".28">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => <path key={i} d={`M${60 + i * 66} 300 L${230 + i * 10} 215`} />)}
          {[0, 1, 2, 3].map((i) => <path key={i} d={`M${40 + i * 14} ${288 - i * 24} L${480 - i * 14} ${288 - i * 24}`} />)}
        </g>
        <g className="stroke-blue" strokeWidth="2.5">
          <rect x="92" y="60" width="26" height="170" rx="2" className="fill-blue/10" />
          <rect x="402" y="60" width="26" height="170" rx="2" className="fill-blue/10" />
          <rect x="92" y="40" width="336" height="28" rx="2" className="fill-blue/10" />
        </g>
        <rect x="240" y="48" width="40" height="12" rx="2" className="fill-ok stroke-none" />
        <g className="stroke-ink" strokeWidth="2.5">
          <rect x="170" y="110" width="180" height="120" rx="3" className="fill-blue/10" />
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <path key={i} d={`M${186 + i * 20} 112 V228`} className="stroke-blue" strokeWidth="1" opacity=".5" />)}
        </g>
        <g className="stroke-gold" strokeWidth="2.5">
          <rect x="196" y="140" width="128" height="56" rx="3" className="fill-surface" />
          <path d="M210 160 H290 M210 178 H262" />
        </g>
      </g>
    </svg>
  );
}
