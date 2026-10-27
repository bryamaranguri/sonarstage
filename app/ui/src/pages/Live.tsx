import { useEffect, useRef, useState } from "react";
import { api, Live, VoiceLine } from "../api";
import { Gauge, Key, Lcd, Led, Lever, ModeSelector, Rack, RackUnit, Readout, SectionMeter, Toggle } from "../components/hardware";
import { loadVoiceSettings, saveVoiceSettings, WakeMode, WAKE_WORDS_BY_MODE } from "./Settings";

const SONG_LOCATOR = /^\s*\d+\.\s/;
const GROUPS = new Set(["EN VIVO", "SECUENCIA", "CUES", "CONTROL", "Secuencia"]);

export default function LivePage({ live }: { live?: Live }) {
  const st = live?.state;
  const songs = live?.setlist ?? [];
  const current = songs.find((s) => s.number === st?.song);
  const order = live?.order ?? songs.map((s) => s.number);
  const sections = current?.sections ?? [];
  const atStart = !st?.section || SONG_LOCATOR.test(st.section);
  const sectionName = atStart ? "Inicio" : st!.section!;
  const bars = st?.section_bars ?? 0;
  const bar = st?.section_bar ?? 0;
  const frac = st ? (st.beat % 4) / 4 : 0;
  const progress = bars ? (bar - 1 + frac) / bars : 0;
  const target = st?.pending ?? st?.landing ?? null;
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();

  const send = async (msg: Record<string, unknown>, tag?: string) => {
    setBusy(tag);
    try {
      const r = await api.cmd(msg);
      setError(r.ok ? undefined : r.error);
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(undefined);
  };

  // which key is current: the n-th occurrence of the name, counting repeated names
  const currentIndex = (() => {
    if (!st || atStart) return -1;
    return sections.findIndex((n) => n === st.section);
  })();
  const songIdx = order.indexOf(st?.song ?? -1);

  return (
    <>
      <div className="header-strip">
        <Readout label="TEMPO" text={st ? st.tempo.toFixed(1) : "—"} unit="BPM" pulseBpm={st?.playing ? st.tempo : 0} />
        <Readout label="COMPÁS" text={bars ? `${bar}/${bars}` : "—"} />
        <div className="hs-divider" />
        <div className="hs-center">
          <div className="hs-actions">
            <button className="arrow" onClick={() => songIdx > 0 && send({ cmd: "song", number: order[songIdx - 1] })} aria-label="Canción anterior">←</button>
            <span className="vsep" />
            <button className="arrow" onClick={() => send({ cmd: "next_song" })} aria-label="Siguiente canción">→</button>
            <span className="spacer" />
            <button className="text-btn" onClick={() => send({ cmd: "play" })}>PLAY</button>
            <button className="text-btn" onClick={() => send({ cmd: "stop" })}>STOP</button>
          </div>
          <label className="preset-select">
            <select value={st?.song ?? ""} onChange={(e) => send({ cmd: "song", number: Number(e.target.value) })}>
              {!st && <option value="">Abre un show en Ableton</option>}
              {order.map((n) => {
                const s = songs.find((x) => x.number === n);
                return s ? <option key={n} value={n}>{`${n}. ${s.title}`}</option> : null;
              })}
            </select>
            <span className="chev">⌄</span>
          </label>
        </div>
        <div className="hs-divider" />
        <div className="hs-toggles">
          <div className="toggle-row">
            AUTOSTOP
            <button className={`switch ${st?.autostop ? "on" : ""}`} onClick={() => send({ cmd: "autostop", on: !st?.autostop })} aria-label="Parada automática" />
          </div>
          <div className="toggle-row dimmed">
            GUÍA INTELIGENTE <Led on={!!st?.guide_quiet} color="amber" />
          </div>
        </div>
      </div>

      {!live?.ok && (
        <div className="banner">{live?.error ?? "Conectando con el motor…"}</div>
      )}
      {error && <div className="banner warn" onClick={() => setError(undefined)}>{error}</div>}

      <Rack>
        <RackUnit title="SECUENCIA" subtitle={st?.song_title ? `${st.song}. ${st.song_title}` : "Sin show abierto"} side={
          <div className="side-col transport">
            <Key label="PLAY" icon="play" light={!!st?.playing} lightColor="green" onClick={() => send({ cmd: "play" }, "play")} />
            <Key label="STOP" icon="stop" onClick={() => send({ cmd: "stop" }, "stop")} />
          </div>
        }>
          <div className="seq-grid">
            <div className="seq-meter">
              <SectionMeter progress={progress} lastBarFrom={bars ? (bars - 1) / bars : 1} label={sectionName.toUpperCase()}
                sub={bars ? `COMPÁS ${bar} DE ${bars}` : "DETENIDO"} bars={bars} />
              <Lcd className="lcd-seq">
                <div className="lcd-row"><span className="lcd-key">CANCIÓN</span><span className="lcd-key">TEMPO</span></div>
                <div className="lcd-row big">
                  <span className="amber">{st?.song_title ?? "—"}</span>
                  <span>{st ? st.tempo.toFixed(1) : "—"}</span>
                </div>
                <div className="lcd-row">
                  <span className="lcd-key">{target ? "VA A" : "DESPUÉS"}</span>
                  <span className={target ? "amber blink-soft" : ""}>{target ?? (st?.next_song ?? "—")}</span>
                </div>
                <Gauge label="SECCIÓN" value={bars ? (bar - 1 + frac) / bars : 0} text={bars ? `${bar}/${bars}` : "—"} />
                <Gauge label="CANCIÓN" value={sections.length ? (currentIndex + 1) / sections.length : 0}
                  text={sections.length ? `${Math.max(0, currentIndex + 1)}/${sections.length}` : "—"} />
              </Lcd>
            </div>
            <div className="seq-buttons">
              <Key label="REPETIR" onClick={() => send({ cmd: "repeat" })} light={!!target && target === st?.section} blink />
              <Key label="SIGUIENTE" onClick={() => send({ cmd: "next_section" })} light={!!target && target !== st?.section} blink />
              <Key label="CANCELAR" onClick={() => send({ cmd: "cancel" })} light={!!st?.pending} lightColor="red" />
              <Key label="SIG. CANCIÓN" onClick={() => send({ cmd: "next_song" })} />
              <div className="bracket" aria-hidden />
              <ModeSelector title="SALTO" value={(st?.jump_mode ?? "section") as "section" | "bar" | "now"}
                options={[{ id: "section", label: "SECCIÓN" }, { id: "bar", label: "COMPÁS" }, { id: "now", label: "YA" }]}
                onChange={(mode) => send({ cmd: "jump_mode", mode })} />
              <Toggle on={!!st?.loop} top="BUCLE" bottom="SEGUIR" label="Bucle"
                onClick={() => send({ cmd: st?.loop ? "release" : "hold" })} />
            </div>
          </div>
        </RackUnit>

        <RackUnit title="SECCIONES" subtitle="Toca una para ir al terminar la actual" compact>
          <div className="section-keys">
            {sections.length === 0 && <div className="empty-keys">Sin secciones: abre un show en Ableton</div>}
            {sections.map((name, i) => {
              const isCurrent = i === currentIndex;
              const isTarget = !!target && name === target && i !== currentIndex &&
                sections.slice(currentIndex + 1).indexOf(name) + currentIndex + 1 === i;
              return (
                <button key={i} className={`key ${isCurrent ? "current" : ""} ${isTarget ? "target" : ""}`}
                  onClick={() => send({ cmd: "goto", section: name })}>
                  <span className="key-led" />
                  <span className="key-name">{name}</span>
                </button>
              );
            })}
          </div>
        </RackUnit>

        <RackUnit title="EN VIVO" subtitle="Respaldo de cada músico · ON suena" compact>
          <Tracks live={live} send={send} />
        </RackUnit>

        <VoiceUnit />
      </Rack>
      {busy && <span className="sr-only">enviando</span>}
    </>
  );
}

function Tracks({ live, send }: { live?: Live; send: (m: Record<string, unknown>) => void }) {
  const tracks = (live?.tracks ?? []).filter((t) => !GROUPS.has(t) && !/^(HX|Consola|MIDI)/i.test(t));
  const mutes = live?.mutes ?? {};
  if (!tracks.length) return <div className="empty-keys dark-text">Las pistas aparecen al abrir el show</div>;
  return (
    <div className="tracks">
      {tracks.map((t) => {
        const on = !mutes[t];
        return (
          <Toggle key={t} look="push" on={on} label={t.toUpperCase()} onClick={() => send({ cmd: "mute", track: t, on })} />
        );
      })}
    </div>
  );
}

function VoiceUnit() {
  const [lines, setLines] = useState<VoiceLine[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string>();
  const since = useRef(0);
  useEffect(() => {
    let alive = true;
    let t: number;
    const tick = async () => {
      try {
        const v = await api.voice(since.current);
        if (!alive) return;
        setRunning(v.running);
        if (v.lines.length) {
          since.current = v.lines[v.lines.length - 1].n;
          setLines((old) => [...old, ...v.lines].slice(-60));
        }
      } catch { /* engine away: keep the last lines */ }
      if (alive) t = window.setTimeout(tick, 400);
    };
    tick();
    return () => { alive = false; window.clearTimeout(t); };
  }, []);

  const [settings, setSettings] = useState(loadVoiceSettings);
  const start = (s = settings) => api.voiceStart({ ...s, wake: WAKE_WORDS_BY_MODE[s.wake] });
  const toggle = async () => {
    setErr(undefined);
    try {
      if (running) await api.voiceStop();
      else await start();
    } catch (e: any) {
      setErr(e.message);
    }
  };
  const setWake = async (wake: WakeMode) => {
    const next = { ...settings, wake };
    setSettings(next);
    saveVoiceSettings(next);
    if (running) {                                   // the listener takes the words when it starts
      try { await api.voiceStop(); await start(next); } catch (e: any) { setErr(e.message); }
    }
  };
  const shown = lines.slice(-4);
  return (
    <RackUnit title="VOZ" subtitle="Control por voz" side={
      <div className="side-col">
        <Toggle look="push" on={running} label="POWER" onClick={toggle} />
      </div>
    }>
      <div className="voice-grid">
        <Lcd className="lcd-voice">
          <div className="lcd-row">
            <span className="lcd-key">{running ? "ESCUCHANDO" : "APAGADA"}</span>
            <span className="lcd-key">{settings.device ? `${String(settings.device).toUpperCase()} · ENTRADA ${settings.channel}` : "ELIGE LA ENTRADA EN AJUSTES"}</span>
          </div>
          {err && <div className="lcd-line red">{err}</div>}
          {shown.length === 0 && !err && <div className="lcd-line dim">{settings.wake === "secuencia" ? "«Secuencia, vamos al coro»" : settings.wake === "banda" ? "«Banda, vamos al coro»" : "«Banda, vamos al coro» · «Secuencia, repetimos»"}</div>}
          {shown.map((l) => (
            <div key={l.n} className={`lcd-line ${l.text.includes("✓") ? "ok" : l.text.includes("✗") || l.text.includes("⚠") ? "red" : ""}`}>
              {l.text.trim()}
            </div>
          ))}
        </Lcd>
        <Lever label="ACTIVACIÓN" value={settings.wake} onChange={setWake}
          options={[{ id: "ambas", label: "AMBAS" }, { id: "secuencia", label: "SECUENCIA" }, { id: "banda", label: "BANDA" }]} />
      </div>
    </RackUnit>
  );
}
