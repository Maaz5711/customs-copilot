// The port as one flat sketch: what people see when the 3D story is not used (no JavaScript, reduced motion, a low-power device, or before it loads).
// Ship at the quay, crane, the checked container with its code, the clearing agent, and the truck leaving through the green customs gate.
// Colours come from the .sk-* classes in globals.css, so it follows light and dark mode.
export function PortSketch({ className }: { className?: string }) {
  const ship = [[150, "sk-blue"], [196, "sk-teal"], [242, "sk-red"], [288, "sk-yellow"], [150, "sk-violet"], [242, "sk-blue"]] as const;
  return (
    <svg viewBox="0 0 720 300" role="img" aria-label="Sketch of a port: a ship at the quay, a crane, a checked container with its tariff code, a clearing agent, and a truck leaving through a green customs gate" className={`sketch ${className ?? ""}`}>
      {/* sun, water, waves */}
      <circle cx="640" cy="50" r="24" className="sk-sun" />
      <rect x="0" y="150" width="372" height="40" className="sk-water" />
      <path d="M372 150 V190" className="sk-line" />
      {[20, 90, 160, 230, 300].map((x, i) => <path key={x} d={`M${x} ${165 + (i % 2) * 12} q8 -6 16 0 t16 0`} className="sk-wave" />)}

      {/* ship */}
      <path d="M40 150 L340 150 L364 118 L40 118 Z" className="sk-navy" />
      <rect x="48" y="80" width="34" height="38" className="sk-paper" />
      <rect x="58" y="66" width="12" height="14" className="sk-red" />
      {ship.map(([x, c], i) => <rect key={i} x={x - 52} y={i < 4 ? 98 : 78} width="44" height="20" className={c} transform={`translate(${i < 4 ? 0 : 46 * (i - 4)} 0)`} />)}

      {/* crane */}
      <g className="sk-line">
        <path d="M390 190 V40 M470 190 V40 M390 40 H470 M390 110 H470" />
        <path d="M250 40 H500 M430 40 L430 12 L250 40 M430 12 L500 40" />
      </g>
      <rect x="420" y="36" width="24" height="10" className="sk-yellow" />
      <path d="M428 46 V96 M436 46 V96" className="sk-line" />

      {/* quay and road */}
      <path d="M0 190 H720 M0 236 H720 M0 213 H720" className="sk-line sk-thin" />

      {/* checked container with its code, and the duty layers above it */}
      <rect x="390" y="146" width="84" height="44" className="sk-orange" />
      <rect x="398" y="154" width="68" height="22" className="sk-paper" />
      <text x="432" y="169" textAnchor="middle" className="sk-text">8507.6000</text>
      {["sk-blue", "sk-teal", "sk-violet", "sk-orange", "sk-yellow", "sk-red"].map((c, i) => <rect key={c} x="398" y={140 - i * 8} width="68" height="6" className={c} />)}

      {/* clearing agent with a tablet */}
      <g transform="translate(500 150)">
        <circle cx="0" cy="-6" r="6" className="sk-skin" />
        <path d="M-7 -11 Q0 -20 7 -11 Z" className="sk-yellow" />
        <rect x="-8" y="0" width="16" height="20" className="sk-vest" />
        <path d="M-5 20 V38 M5 20 V38" className="sk-line" />
        <path d="M-8 4 L-18 -4" className="sk-line" />
        <rect x="-26" y="-10" width="10" height="8" className="sk-teal" />
      </g>

      {/* customs gate with a green light, barrier up */}
      <rect x="580" y="120" width="8" height="70" className="sk-paper" />
      <rect x="568" y="112" width="110" height="12" className="sk-navy" />
      <rect x="614" y="104" width="18" height="8" className="sk-ok" />
      <path d="M588 186 L628 150" className="sk-line sk-thick" />

      {/* truck leaving with a container */}
      <g transform="translate(600 0)">
        <rect x="0" y="196" width="70" height="30" className="sk-teal" />
        <rect x="70" y="200" width="24" height="26" className="sk-red" />
        <rect x="76" y="204" width="12" height="9" className="sk-paper" />
        <path d="M0 228 H96" className="sk-line" />
        {[12, 26, 80].map((x) => <circle key={x} cx={x} cy="230" r="6" className="sk-tyre" />)}
      </g>
    </svg>
  );
}
