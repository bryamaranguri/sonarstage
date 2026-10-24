import { useState } from "react";
import { Fader, Gauge, HwButton, Lcd, Led, Lever, ModeSelector, Rack, RackUnit, SectionMeter, TapButton, Toggle } from "../components/hardware";

const PALETTE: [string, string, string][] = [
  ["--room", "Sala", "fondo de madera"],
  ["--chassis", "Chasis", "todos los equipos"],
  ["--trim", "Borde", "filete y detalles"],
  ["--control", "Control", "lo que se toca"],
  ["--amber", "Ámbar", "pantallas, lo que va a pasar"],
  ["--green", "Verde", "encendido, suena"],
  ["--red", "Rojo", "parar, error"],
];

/** Every piece of hardware on one page, to choose and tune them (#muestras). */
export default function SamplesPage() {
  const [a, setA] = useState(true);
  const [b, setB] = useState(false);
  const [mode, setMode] = useState<"section" | "bar" | "now">("section");
  const [lev, setLev] = useState<"ambas" | "secuencia" | "banda">("ambas");
  const [f, setF] = useState(0.6);
  return (
    <Rack>
      <RackUnit title="COLORES" subtitle="Una familia, un trabajo por color" compact>
        <div className="swatches">
          {PALETTE.map(([v, name, job]) => (
            <div key={v} className="swatch"><span style={{ background: `var(${v})` }} /><b>{name}</b><small>{job}</small></div>
          ))}
        </div>
      </RackUnit>
      <RackUnit title="ON / OFF" subtitle="Dos opciones para comparar" compact>
        <div className="tracks">
          <div className="track"><Led on={a} /><Toggle on={a} onClick={() => setA(!a)} /><span className="track-name">PALANCA</span></div>
          <div className="track"><Toggle look="latch" on={a} top="ON" bottom="OFF" onClick={() => setA(!a)} /><span className="track-name">TECLA CON LUZ</span></div>
          <div className="track"><Led on={b} /><Toggle on={b} onClick={() => setB(!b)} /><span className="track-name">PALANCA</span></div>
          <div className="track"><Toggle look="latch" on={b} top="ON" bottom="OFF" onClick={() => setB(!b)} /><span className="track-name">TECLA CON LUZ</span></div>
        </div>
      </RackUnit>
      <RackUnit title="CONTROLES" compact>
        <div className="tracks">
          <HwButton label="DOMO" />
          <HwButton label="OSCURO" tone="dark" led ledColor="red" />
          <TapButton label="TAP" />
          <ModeSelector title="SALTO" value={mode} onChange={setMode}
            options={[{ id: "section", label: "SECCIÓN" }, { id: "bar", label: "COMPÁS" }, { id: "now", label: "YA" }]} />
          <Lever label="ACTIVACIÓN" value={lev} onChange={setLev}
            options={[{ id: "ambas", label: "AMBAS" }, { id: "secuencia", label: "SECUENCIA" }, { id: "banda", label: "BANDA" }]} />
          <Fader label="NIVEL" value={f} onChange={setF} cap="orange" text={`${Math.round(f * 100)} %`} />
        </div>
      </RackUnit>
      <RackUnit title="LECTURAS" compact>
        <div className="tracks">
          <SectionMeter progress={0.62} lastBarFrom={0.75} label="CORO" sub="COMPÁS 3 DE 4" bars={4} />
          <Lcd className="lcd-seq">
            <div className="lcd-row"><span className="lcd-key">MODO</span></div>
            <div className="lcd-row big"><span className="amber">CORO 2</span><span>128.0</span></div>
            <Gauge label="SECCIÓN" value={0.62} text="3/4" />
            <Gauge label="CANCIÓN" value={0.4} text="9/23" />
          </Lcd>
        </div>
      </RackUnit>
    </Rack>
  );
}
