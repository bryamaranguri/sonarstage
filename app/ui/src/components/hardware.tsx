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
export function RackUnit({ title, subtitle, children, side, compact }: {
  title: string; subtitle?: string; children: React.ReactNode; side?: React.ReactNode; tone?: string; compact?: boolean;
}) {
  return (
    <section className={`rack-unit ${compact ? "compact" : ""}`}>
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

/** Bat toggle switch (ON up / OFF down). */
export function Toggle({ on, onClick, top = "ON", bottom = "OFF", label }: {
  on: boolean; onClick?: () => void; top?: string; bottom?: string; label?: string;
}) {
  return (
    <div className="toggle-wrap">
      <span className="silk">{top}</span>
      <button className={`bat ${on ? "on" : ""}`} onClick={onClick} aria-pressed={on} aria-label={label ?? top}>
        <svg viewBox="0 0 40 56" aria-hidden>
          <polygon points="20,10 33,18 33,38 20,46 7,38 7,18" className="bat-nut" />
          <circle cx="20" cy="28" r="7" className="bat-base" />
          <line x1="20" y1="28" x2="20" y2={on ? 6 : 50} className="bat-lever" />
          <circle cx="20" cy={on ? 7 : 49} r="4.5" className="bat-tip" />
        </svg>
      </button>
      <span className="silk">{bottom}</span>
    </div>
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
export function SectionMeter({ progress, lastBarFrom, label, sub }: {
  progress: number; lastBarFrom: number; label: string; sub: string;
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
  const ticks = Array.from({ length: 11 }, (_, i) => i / 10);
  const p = Math.max(0, Math.min(1, progress));
  const hot = Math.min(Math.max(lastBarFrom, 0), 1);
  const [nx, ny] = pt(p, r + 10);
  return (
    <svg viewBox="0 0 300 180" className="meter" role="img" aria-label={`${label}, ${sub}`}>
      <path d={arc(0, hot, r)} className="meter-scale" />
      <path d={arc(hot, 1, r - 4)} className="meter-hot" />
      {ticks.map((f) => {
        const [x0, y0] = pt(f, r - 2), [x1, y1] = pt(f, r + (f % 0.5 === 0 ? 16 : 9));
        return <line key={f} x1={x0} y1={y0} x2={x1} y2={y1} className={f >= hot ? "meter-tick hot" : "meter-tick"} />;
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
