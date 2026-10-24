// "Hardware" pieces drawn in SVG/CSS: rack units with screws and wooden cheeks, knobs,
// a needle meter, an LCD, square buttons with LEDs. All original drawings.
import React from "react";

export function Screw({ style }: { style?: React.CSSProperties }) {
  return (
    <svg className="screw" viewBox="0 0 20 20" style={style} aria-hidden>
      <defs>
        <radialGradient id="screwG" cx="40%" cy="35%" r="70%">
          <stop offset="0" stopColor="#5d6274" />
          <stop offset="1" stopColor="#1c1f2a" />
        </radialGradient>
      </defs>
      <circle cx="10" cy="10" r="8.5" fill="url(#screwG)" stroke="#11131b" strokeWidth="1.2" />
      <circle cx="10" cy="10" r="3.2" fill="#0f1118" />
    </svg>
  );
}

/** A slate rack unit with a copper rim: big title, a small subtitle, controls below. */
export function RackUnit({ title, subtitle, children, side, compact, tone }: {
  title: string; subtitle?: string; children: React.ReactNode; side?: React.ReactNode; tone?: "slate" | "gold"; compact?: boolean;
}) {
  return (
    <section className={`rack-unit ${compact ? "compact" : ""} ${tone === "gold" ? "gold" : ""}`}>
      <Screw style={{ left: 16, top: 16 }} />
      <Screw style={{ left: 16, bottom: 16 }} />
      <Screw style={{ right: 16, top: 16 }} />
      <Screw style={{ right: 16, bottom: 16 }} />
      <header className="unit-head">
        <h2 className="unit-title">{title}</h2>
        {subtitle && <span className="unit-sub">{subtitle}</span>}
      </header>
      <div className="unit-main">
        <div className="unit-body">{children}</div>
        {side && <div className="unit-side">{side}</div>}
      </div>
    </section>
  );
}

/** Units standing on copper feet, over a dark shelf. */
export function Rack({ children }: { children: React.ReactNode }) {
  return (
    <div className="rack">
      <div className="rack-stack">{children}</div>
      <div className="feet"><span /><span /></div>
    </div>
  );
}

/** Bat toggle switch (ON up / OFF down): chrome lever on a hex nut. `look="latch"` draws
 * the alternative: a square latching key with its own light. */
export function Toggle({ on, onClick, top = "ON", bottom = "OFF", label, look = "bat" }: {
  on: boolean; onClick?: () => void; top?: string; bottom?: string; label?: string; look?: "bat" | "latch";
}) {
  if (look === "latch") {
    return (
      <div className="toggle-wrap latch-wrap">
        <button className={`latch ${on ? "on" : ""}`} onClick={onClick} aria-pressed={on} aria-label={label ?? top}>
          <span className="latch-light" />
        </button>
        <span className="silk">{on ? top : bottom}</span>
      </div>
    );
  }
  return (
    <div className="toggle-wrap">
      <span className={`silk ${on ? "lit" : "dim"}`}>{top}</span>
      <button className={`bat ${on ? "on" : ""}`} onClick={onClick} aria-pressed={on} aria-label={label ?? top}>
        <BatSvg on={on} />
      </button>
      <span className={`silk ${on ? "dim" : "lit"}`}>{bottom}</span>
    </div>
  );
}

let batIds = 0;
/** A chrome bat lever on a dark bronze hex nut, lit from the top left. Drawn once per
 * instance with its own gradient ids. */
function BatSvg({ on }: { on: boolean }) {
  const id = React.useMemo(() => "bat" + ++batIds, []);
  const cx = 50, cy = 62;
  // hex nut corners (flat sides left/right), each facet shaded by where the light falls
  const R = 30;
  const P = Array.from({ length: 6 }, (_, i) => {
    const t = ((i * 60 - 90) * Math.PI) / 180;
    return [cx + R * Math.cos(t), cy + R * Math.sin(t)];
  });
  const inner = Array.from({ length: 6 }, (_, i) => {
    const t = ((i * 60 - 90) * Math.PI) / 180;
    return [cx + 21 * Math.cos(t), cy + 21 * Math.sin(t)];
  });
  const facetShade = ["#a58a83", "#7a605a", "#4a3734", "#3a2a28", "#5d4744", "#8d726b"];
  // lever: from the bushing toward the tip, foreshortened (seen a bit from above)
  const tip = on ? { x: cx + 3, y: cy - 50 } : { x: cx + 3, y: cy + 46 };
  const dir = on ? -1 : 1;
  const baseW = 3.9, tipW = 3.1, from = cy + dir * 1.2;        // the lever leaves the slot in the dome
  const lever = `M${cx - baseW} ${from} L${tip.x - tipW} ${tip.y - dir * 2} L${tip.x + tipW} ${tip.y - dir * 2} L${cx + baseW} ${from} Z`;
  return (
    <svg viewBox="0 0 100 124" aria-hidden>
      <defs>
        <radialGradient id={id + "collar"} cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#f2e6e1" /><stop offset=".35" stopColor="#a8908a" />
          <stop offset=".75" stopColor="#4b3936" /><stop offset="1" stopColor="#2a1e1c" />
        </radialGradient>
        <linearGradient id={id + "lever"} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5d5654" /><stop offset=".22" stopColor="#d8d2cf" />
          <stop offset=".38" stopColor="#ffffff" /><stop offset=".6" stopColor="#a39c99" />
          <stop offset=".85" stopColor="#4a4442" /><stop offset="1" stopColor="#77706e" />
        </linearGradient>
        <radialGradient id={id + "tip"} cx="38%" cy="30%" r="70%">
          <stop offset="0" stopColor="#ffffff" /><stop offset=".35" stopColor="#e6e0dd" />
          <stop offset=".8" stopColor="#7a7371" /><stop offset="1" stopColor="#3d3735" />
        </radialGradient>
        <radialGradient id={id + "dome"} cx="36%" cy="30%" r="80%">
          <stop offset="0" stopColor="#ffffff" /><stop offset=".25" stopColor="#d6ccc8" />
          <stop offset=".6" stopColor="#7d6c68" /><stop offset="1" stopColor="#2f2422" />
        </radialGradient>
        <filter id={id + "blur"} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.2" />
        </filter>
      </defs>
      {/* shadow of the nut on the panel */}
      <ellipse cx={cx + 6} cy={cy + 9} rx="31" ry="27" fill="rgba(0,0,0,.55)" filter={`url(#${id}blur)`} />
      {/* nut facets */}
      {P.map((p0, i) => {
        const p1 = P[(i + 1) % 6], q0 = inner[i], q1 = inner[(i + 1) % 6];
        return <polygon key={i} points={`${p0[0]},${p0[1]} ${p1[0]},${p1[1]} ${q1[0]},${q1[1]} ${q0[0]},${q0[1]}`} fill={facetShade[i]} />;
      })}
      <polygon points={inner.map((q) => q.join(",")).join(" ")} fill="#5a4642" />
      <polygon points={P.map((q) => q.join(",")).join(" ")} fill="none" stroke="#1d1413" strokeWidth="1.4" />
      {/* threaded collar */}
      <circle cx={cx} cy={cy} r="17" fill={`url(#${id}collar)`} stroke="#1f1615" strokeWidth="1" />
      {[15, 13, 11].map((r) => <circle key={r} cx={cx} cy={cy} r={r} fill="none" stroke="rgba(30,20,19,.5)" strokeWidth=".7" />)}
      {/* domed pivot the lever goes into: a shiny cap with a dark slot */}
      <circle cx={cx} cy={cy + 1.5} r="10.5" fill="rgba(0,0,0,.45)" filter={`url(#${id}blur)`} />
      <circle cx={cx} cy={cy} r="9.5" fill={`url(#${id}dome)`} stroke="#2a201e" strokeWidth=".8" />
      <ellipse cx={cx} cy={cy + dir * 1.2} rx="4.6" ry="3.4" fill="#1b1413" />
      {/* lever shadow, the lever from inside the slot, its rim and the ball */}
      <path d={lever} transform="translate(5 5)" fill="rgba(0,0,0,.45)" filter={`url(#${id}blur)`} />
      <path d={lever} fill={`url(#${id}lever)`} stroke="#3a3432" strokeWidth=".7" />
      <path d={`M${cx - 4.6} ${cy + dir * 1.2} A4.6 3.4 0 0 ${on ? 0 : 1} ${cx + 4.6} ${cy + dir * 1.2}`}
        fill="none" stroke="rgba(255,255,255,.55)" strokeWidth=".9" />
      <ellipse cx={tip.x} cy={tip.y} rx="6.6" ry={on ? 5.4 : 5.8} fill={`url(#${id}tip)`} stroke="#3a3432" strokeWidth=".7" />
      <ellipse cx={tip.x - 2.2} cy={tip.y - 2} rx="2.1" ry="1.4" fill="rgba(255,255,255,.95)" />
    </svg>
  );
}

/** Vertical fader with a tick scale. value 0..1. */
export function Fader({ value, onChange, label, cap = "cream", text }: {
  value: number; onChange?: (v: number) => void; label: string; cap?: "cream" | "orange"; text?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const set = (clientY: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || !onChange) return;
    onChange(Math.max(0, Math.min(1, 1 - (clientY - r.top) / r.height)));
  };
  const drag = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    set(e.clientY);
  };
  return (
    <div className="fader">
      <div className="fader-scale left" />
      <div className="fader-track" ref={ref} onPointerDown={drag}
        onPointerMove={(e) => e.buttons && set(e.clientY)} role="slider" aria-label={label}
        aria-valuenow={Math.round(value * 100)} tabIndex={0}
        onKeyDown={(e) => { if (e.key === "ArrowUp") onChange?.(Math.min(1, value + 0.05)); if (e.key === "ArrowDown") onChange?.(Math.max(0, value - 0.05)); }}>
        <div className={`fader-cap ${cap}`} style={{ bottom: `calc(${value * 100}% - 14px)` }} />
      </div>
      <div className="fader-scale right" />
      <span className="silk fader-label">{label}</span>
      {text && <span className="fader-text">{text}</span>}
    </div>
  );
}

export function Led({ on, color = "green", blink }: { on: boolean; color?: "amber" | "green" | "red" | "mint"; blink?: boolean }) {
  return <span className={`led ${color} ${on ? "on" : ""} ${on && blink ? "blink" : ""}`} aria-hidden />;
}

/** Round cream dome you press (the knob style of a vintage tank, as a button). */
export function HwButton({ label, onClick, tone = "cream", led, ledColor = "green", ledBlink, disabled, title }: {
  label: string; onClick?: () => void; tone?: "cream" | "orange" | "dark"; led?: boolean; ledColor?: "amber" | "green" | "red" | "mint";
  ledBlink?: boolean; disabled?: boolean; wide?: boolean; title?: string;
}) {
  return (
    <div className="hw-button-wrap">
      <button className={`dome ${tone}`} onClick={onClick} disabled={disabled} title={title} aria-label={label}>
        <span className="dome-top" />
        {led !== undefined && <span className={`dome-led ${led ? "on" : ""} ${ledColor} ${led && ledBlink ? "blink" : ""}`} />}
      </button>
      <span className="silk">{label}</span>
    </div>
  );
}

/** Dark display with amber characters. */
export function Lcd({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`lcd ${className}`}>{children}</div>;
}

/** Flat header knob (white face, arc track), as a readout. value in 0..1. */
export function FlatKnob({ label, value, text, dim, toggle, onToggle }: {
  label: string; value: number; text: string; dim?: boolean; toggle?: boolean; onToggle?: () => void;
}) {
  const a0 = -135, a1 = 135;
  const ang = a0 + (a1 - a0) * Math.max(0, Math.min(1, value));
  const r = 38, cx = 50, cy = 50;
  const pt = (deg: number, rr: number) => {
    const t = ((deg - 90) * Math.PI) / 180;
    return [cx + rr * Math.cos(t), cy + rr * Math.sin(t)];
  };
  const arc = (from: number, to: number) => {
    const [x0, y0] = pt(from, r), [x1, y1] = pt(to, r);
    const large = to - from > 180 ? 1 : 0;
    return `M${x0} ${y0} A${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  const [ix, iy] = pt(ang, 26);
  return (
    <div className={`flat-knob ${dim ? "dim" : ""}`}>
      <div className="fk-label">
        {label}
        {toggle !== undefined && (
          <button className={`switch ${toggle ? "on" : ""}`} onClick={onToggle} aria-label={label} />
        )}
      </div>
      <svg viewBox="0 0 100 100" className="fk-dial">
        <path d={arc(a0, a1)} className="fk-track" />
        <path d={arc(a0, ang)} className="fk-fill" />
        <circle cx={cx} cy={cy} r="30" className="fk-face" />
        <line x1={cx} y1={cy} x2={ix} y2={iy} className="fk-pointer" />
      </svg>
      <div className="fk-value">{text}</div>
    </div>
  );
}

/** Needle meter for "how far into the section": the last bar is the orange zone, where a
 * pending jump fires. progress 0..1, lastBarFrom = where the last bar starts (0..1). */
export function SectionMeter({ progress, lastBarFrom, label, sub, bars = 0 }: {
  progress: number; lastBarFrom: number; label: string; sub: string; bars?: number;
}) {
  const a0 = -38, a1 = 38, cx = 150, cy = 236, r = 196;     // pivot below the window, like a VU
  const pt = (frac: number, rr: number) => {
    const deg = a0 + (a1 - a0) * frac;
    const t = ((deg - 90) * Math.PI) / 180;
    return [cx + rr * Math.cos(t), cy + rr * Math.sin(t)];
  };
  const arc = (f0: number, f1: number, rr: number) => {
    const [x0, y0] = pt(f0, rr), [x1, y1] = pt(f1, rr);
    return `M${x0} ${y0} A${rr} ${rr} 0 0 1 ${x1} ${y1}`;
  };
  const ticks = bars > 0 && bars <= 16 ? Array.from({ length: bars + 1 }, (_, i) => i / bars) : Array.from({ length: 11 }, (_, i) => i / 10);
  const p = Math.max(0, Math.min(1, progress));
  const hot = Math.min(Math.max(lastBarFrom, 0), 1);
  const numbers = bars > 0 && bars <= 16 ? Array.from({ length: bars }, (_, i) => ({ f: (i + 0.5) / bars, n: i + 1 })) : [];
  const [nx, ny] = pt(p, r + 10);
  return (
    <svg viewBox="0 0 300 180" className="meter" role="img" aria-label={`${label}, ${sub}`}>
      <path d={arc(0, hot, r)} className="meter-scale" />
      <path d={arc(hot, 1, r - 4)} className="meter-hot" />
      {ticks.map((f) => {
        const major = numbers.length ? true : f % 0.5 === 0;
        const [x0, y0] = pt(f, r - 2), [x1, y1] = pt(f, r + (major ? 14 : 9));
        return <line key={f} x1={x0} y1={y0} x2={x1} y2={y1} className={f > hot + 1e-6 ? "meter-tick hot" : "meter-tick"} />;
      })}
      {numbers.map(({ f, n }) => {
        const [x, y] = pt(f, r + 24);
        return <text key={n} x={x} y={y + 5} className={f > hot ? "meter-num hot" : "meter-num"}>{n}</text>;
      })}
      <text x={cx} y={112} className="meter-label">{label}</text>
      <text x={cx} y={134} className="meter-sub">{sub}</text>
      <line x1={cx} y1={cy} x2={nx} y2={ny} className="meter-needle" style={{ transition: "all 120ms linear" }} />
      <rect x={cx - 26} y={156} width={52} height={30} rx={10} className="meter-hub" />
    </svg>
  );
}

/** Line icons for the top navigation (original drawings). */
export const Icons = {
  live: (
    <svg viewBox="0 0 48 48"><rect x="10" y="5" width="28" height="38" rx="3" /><path d="M16 26h4l3-8 4 14 3-6h3" /></svg>
  ),
  library: (
    <svg viewBox="0 0 48 48"><rect x="6" y="14" width="36" height="22" rx="2" /><path d="M6 20h36M12 30h10" /></svg>
  ),
  show: (
    <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="17" /><circle cx="24" cy="24" r="6" /><path d="M24 7v4" /></svg>
  ),
  matrix: (
    <svg viewBox="0 0 48 48"><path d="M10 8v32M24 8v32M38 8v32" /><circle cx="10" cy="30" r="3.5" /><circle cx="24" cy="16" r="3.5" /><circle cx="38" cy="26" r="3.5" /></svg>
  ),
  settings: (
    <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="7" /><path d="M24 6v6M24 36v6M6 24h6M36 24h6M11.3 11.3l4.2 4.2M32.5 32.5l4.2 4.2M11.3 36.7l4.2-4.2M32.5 15.5l4.2-4.2" /></svg>
  ),
};

/** Serrated white selector knob with 3–4 positions on an arc (dots), labels at the ends. */
export function ModeSelector<T extends string>({ options, value, onChange, title }: {
  options: { id: T; label: string }[]; value: T; onChange: (v: T) => void; title: string;
}) {
  const n = options.length;
  const span = n <= 3 ? 100 : 130;
  const angleOf = (i: number) => -span / 2 + (span * i) / Math.max(1, n - 1);
  const cx = 110, cy = 112, r = 74;
  const pt = (deg: number, rr: number) => {
    const t = ((deg - 90) * Math.PI) / 180;
    return [cx + rr * Math.cos(t), cy + rr * Math.sin(t)];
  };
  const at = Math.max(0, options.findIndex((o) => o.id === value));
  const [a0x, a0y] = pt(-span / 2 - 14, r), [a1x, a1y] = pt(span / 2 + 14, r);
  const teeth = Array.from({ length: 36 }, (_, i) => i * 10);
  const [px0, py0] = pt(angleOf(at), 30), [px1, py1] = pt(angleOf(at), 46);
  return (
    <div className="mode-selector">
      <svg viewBox="-20 -6 260 206" role="radiogroup" aria-label={title}>
        <defs>
          <radialGradient id="msFace" cx="45%" cy="35%" r="70%">
            <stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#d8d6d1" />
          </radialGradient>
        </defs>
        <path d={`M${a0x} ${a0y} A${r} ${r} 0 0 1 ${a1x} ${a1y}`} className="ms-arc" />
        {options.map((o, i) => {
          const [dx, dy] = pt(angleOf(i), r);
          const [lx, ly] = pt(angleOf(i), r + 30);
          return (
            <g key={o.id} className={`ms-opt ${i === at ? "on" : ""}`} onClick={() => onChange(o.id)} role="radio" aria-checked={i === at}>
              <circle cx={dx} cy={dy} r={5} className="ms-dot" />
              <text x={lx} y={ly + 4} className="ms-label">{o.label}</text>
            </g>
          );
        })}
        <g onClick={() => onChange(options[(at + 1) % n].id)} className="ms-knob">
          <circle cx={cx} cy={cy} r={58} className="ms-ring" />
          {teeth.map((d) => {
            const [x, y] = pt(d, 49);
            return <circle key={d} cx={x} cy={y} r={3.2} className="ms-tooth" />;
          })}
          <circle cx={cx} cy={cy} r={48} fill="url(#msFace)" className="ms-face" />
          <line x1={px0} y1={py0} x2={px1} y2={py1} className="ms-pointer" />
          <text x={cx} y={cy + 4} className="ms-title">{title}</text>
        </g>
      </svg>
    </div>
  );
}

/** Orange 3-way lever (like a sync switch): left / middle / right. */
export function Lever<T extends string>({ options, value, onChange, label }: {
  options: { id: T; label: string }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  const at = Math.max(0, options.findIndex((o) => o.id === value));
  const angle = [-38, 0, 38][at] ?? 0;
  return (
    <div className="lever">
      <div className="lever-labels">
        {options.map((o, i) => (
          <button key={o.id} className={i === at ? "on" : ""} onClick={() => onChange(o.id)}>{o.label}</button>
        ))}
      </div>
      <svg viewBox="0 0 120 70" className="lever-svg" onClick={() => onChange(options[(at + 1) % options.length].id)} role="button" aria-label={label}>
        <path d="M20 8v8l22 14M60 8v14M100 8v8l-22 14" className="lever-guides" />
        <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: "60px 52px", transition: "transform .15s" }}>
          <path d="M54 52 L60 26 L66 52 Z" className="lever-arm" />
        </g>
        <circle cx="60" cy="52" r="14" className="lever-ball" />
      </svg>
      <span className="silk">{label}</span>
    </div>
  );
}

/** A bar gauge for the LCD: label, outlined bar, value. */
export function Gauge({ label, value, text }: { label: string; value: number; text: string }) {
  return (
    <div className="gauge">
      <span className="gauge-label">{label}</span>
      <span className="gauge-bar"><span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></span>
      <span className="gauge-text">{text}</span>
    </div>
  );
}

/** Square soft button (TAP). */
export function TapButton({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <div className="hw-button-wrap">
      <button className="tap" onClick={onClick} aria-label={label}><span /></button>
      <span className="silk">{label}</span>
    </div>
  );
}
