import { useState } from "react";
import { Fader, Gauge, HwButton, Key, Lcd, Lever, ModeSelector, Rack, RackUnit, SectionMeter, Toggle } from "../components/hardware";

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
      <RackUnit title="DOS OPCIONES" subtitle="Deslizante con nombre · botón ON/OFF con luz" compact>
        <div className="tracks">
          <Toggle on={a} top="PLAY" bottom="STOP" onClick={() => setA(!a)} />
          <Toggle on={b} top="BUCLE" bottom="SEGUIR" onClick={() => setB(!b)} />
          <Toggle look="push" on={a} label="POWER" onClick={() => setA(!a)} />
          <Toggle look="push" on={b} label="BATERÍA" onClick={() => setB(!b)} />
        </div>
      </RackUnit>
      <RackUnit title="CONTROLES" compact>
        <div className="tracks">
          <Key label="TECLA" />
          <Key label="PENDIENTE" light blink />
          <Key label="PLAY" icon="play" light lightColor="green" />
          <Key label="STOP" icon="stop" />
          <HwButton label="PERILLA (VALORES)" />
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
