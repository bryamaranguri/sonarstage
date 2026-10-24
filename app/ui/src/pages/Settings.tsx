import { useEffect, useState } from "react";
import { api, Device, Status } from "../api";
import { Fader } from "../components/hardware";

export type WakeMode = "ambas" | "secuencia" | "banda";
export const WAKE_WORDS_BY_MODE: Record<WakeMode, string[]> = { ambas: ["secuencia", "banda"], secuencia: ["secuencia"], banda: ["banda"] };
export type VoiceSettings = { device: string | number | null; channel: number; confirmChannel: number; dryRun: boolean; confirmGain: number; wake: WakeMode };
const KEY = "sonarstage.voice";
const DEFAULTS: VoiceSettings = { device: null, channel: 1, confirmChannel: 2, dryRun: false, confirmGain: 0, wake: "ambas" };

export function loadVoiceSettings(): VoiceSettings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

export function saveVoiceSettings(v: VoiceSettings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(v));
  } catch { /* private window: settings last this session only */ }
}

export default function SettingsPage() {
  const [v, setV] = useState<VoiceSettings>(loadVoiceSettings);
  const [devices, setDevices] = useState<Device[]>();
  const [devErr, setDevErr] = useState<string>();
  const [status, setStatus] = useState<Status>();
  useEffect(() => {
    api.devices().then(setDevices).catch((e) => setDevErr(e.message));
    api.status().then(setStatus).catch(() => {});
  }, []);
  const update = (patch: Partial<VoiceSettings>) => {
    const next = { ...v, ...patch };
    setV(next);
    saveVoiceSettings(next);
  };
  const dev = devices?.find((d) => d.name === v.device || d.index === v.device);

  const gainTo = (v: number) => Math.round((v * 24 - 18) * 2) / 2;      // -18 … +6 dB
  const gainFrom = (db: number) => (db + 18) / 24;
  return (
    <div className="dialog-room">
      <section className="dialog" aria-label="Ajustes">
        <header className="dialog-head"><h2>Ajustes</h2><a href="#live" className="dialog-x" aria-label="Cerrar">✕</a></header>
        <div className="dialog-cols">
          <div className="dialog-col">
            <label className="field">
              <span>Interfaz de audio</span>
              <select value={String(v.device ?? "")} onChange={(e) => update({ device: e.target.value || null })}>
                <option value="">Elegir…</option>
                {devices?.map((d) => <option key={d.index} value={d.name}>{d.name} · {d.inputs} entradas · {d.rate} Hz</option>)}
              </select>
              {devErr && <span className="hint red">{devErr}</span>}
            </label>
            <div className="field-row">
              <label className="field">
                <span>Entrada del micrófono</span>
                <input type="number" min={1} max={dev?.inputs ?? 32} value={v.channel} onChange={(e) => update({ channel: Number(e.target.value) })} />
              </label>
              <label className="field">
                <span>Salida de la confirmación</span>
                <input type="number" min={1} max={dev?.outputs ?? 32} value={v.confirmChannel} onChange={(e) => update({ confirmChannel: Number(e.target.value) })} />
                <span className="hint">La del click</span>
              </label>
            </div>
            <label className="field check">
              <input type="checkbox" checked={v.dryRun} onChange={(e) => update({ dryRun: e.target.checked })} />
              <span>Solo escuchar (no enviar nada a Ableton)</span>
            </label>
            <div className="field">
              <span>Rutas</span>
              <div className="paths">
                {status ? Object.entries(status.config).map(([k, val]) => (
                  <div key={k}><b>{k}</b><code>{val ?? "—"}</code></div>
                )) : "Conectando con el motor…"}
              </div>
            </div>
          </div>
          <div className="dialog-col faders">
            <span className="field-title">Volumen de la confirmación</span>
            <div className="fader-bank">
              <Fader label="VOZ" value={gainFrom(v.confirmGain)} cap="orange" text={`${v.confirmGain > 0 ? "+" : ""}${v.confirmGain.toFixed(1)} dB`}
                onChange={(x) => update({ confirmGain: gainTo(x) })} />
            </div>
            <span className="hint">Se aplica al encender la voz</span>
          </div>
        </div>
      </section>
    </div>
  );
}
