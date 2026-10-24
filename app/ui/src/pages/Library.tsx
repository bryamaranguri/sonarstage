import { useEffect, useState } from "react";
import { api, fmtSemis, fmtTime, Song, SongSummary } from "../api";
import { FlatKnob, Lcd, Rack, RackUnit } from "../components/hardware";

const KIND_CLASS: Record<string, string> = { chorus: "k-chorus", verse: "k-verse", prechorus: "k-pre", bridge: "k-bridge",
  intro: "k-intro", outro: "k-outro", interlude: "k-inter", tag: "k-tag" };

export default function LibraryPage() {
  const [songs, setSongs] = useState<SongSummary[]>();
  const [err, setErr] = useState<string>();
  const [sel, setSel] = useState<string>();
  const [song, setSong] = useState<Song>();
  const [q, setQ] = useState("");
  useEffect(() => { api.library().then((s) => { setSongs(s); setSel((x) => x ?? s[0]?.folder); }).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { if (sel) api.song(sel).then(setSong).catch((e) => setErr(e.message)); }, [sel]);
  const summary = songs?.find((s) => s.folder === sel);
  const shown = (songs ?? []).filter((s) => s.title.toLowerCase().includes(q.toLowerCase()));
  const total = song ? song.sections.reduce((a, s) => Math.max(a, s.startBar + s.bars - 1), 0) : 0;

  return (
    <>
      <div className="header-strip">
        <FlatKnob label="CANCIONES" value={Math.min(1, (songs?.length ?? 0) / 40)} text={String(songs?.length ?? "—")} />
        <FlatKnob label="BPM" value={(summary?.bpm ?? 0) / 200} text={summary ? summary.bpm.toFixed(1) : "—"} />
        <div className="hs-divider" />
        <div className="hs-center">
          <div className="hs-actions"><span className="hs-caption">BUSCAR EN LA BIBLIOTECA</span><span className="spacer" /><span className="text-btn disabled" title="Próximamente desde la app">IMPORTAR…</span></div>
          <label className="preset-select"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Título de la canción" /></label>
        </div>
        <div className="hs-divider" />
        <FlatKnob label="DURACIÓN" value={(summary?.durationS ?? 0) / 600} text={summary ? fmtTime(summary.durationS) : "—"} />
        <FlatKnob label="STEMS" value={(summary?.stems ?? 0) / 32} text={String(summary?.stems ?? "—")} />
      </div>
      {err && <div className="banner warn">{err}</div>}
      <div className="split">
        <div className="browser">
          {shown.map((s) => (
            <button key={s.folder} className={`browser-row ${s.folder === sel ? "sel" : ""}`} onClick={() => setSel(s.folder)}>
              <span className="br-title">{s.title}</span>
              <span className="br-meta">{s.bpm.toFixed(0)} BPM · {fmtTime(s.durationS)} · {s.sections} secciones</span>
            </button>
          ))}
          {songs && shown.length === 0 && <div className="browser-empty">Nada con «{q}»</div>}
        </div>
        <Rack>
          <RackUnit title={summary ? summary.title.toUpperCase() : "CANCIÓN"} subtitle={summary ? `${summary.bpm.toFixed(0)} BPM · ${summary.timeSignature} · ${summary.sections} secciones` : undefined}>
            {summary && song ? (
              <div className="song-detail">
                <Lcd className="lcd-wide">
                  <div className="lcd-row"><span className="lcd-key">TÍTULO</span><span className="lcd-key">TONOS LISTOS</span></div>
                  <div className="lcd-row big"><span className="amber">{summary.title}</span>
                    <span>{[0, ...summary.prepared.filter((p) => p !== 0)].map(fmtSemis).join(" · ")}</span></div>
                  <div className="lcd-row"><span className="lcd-key">ORIGEN</span><span className="path">{summary.source ?? "—"}</span></div>
                </Lcd>
                <div className="timeline" aria-label="Secciones">
                  {song.sections.map((s, i) => (
                    <div key={i} className={`tl-block ${KIND_CLASS[s.kind] ?? ""}`} style={{ flexGrow: s.bars }}
                      title={`${s.name} · compases ${s.startBar}–${s.startBar + s.bars - 1}${s.guide ? ` · guía: «${s.guide}»` : ""}`}>
                      <span>{s.name}</span>
                    </div>
                  ))}
                </div>
                <div className="tl-ruler"><span>1</span><span>{total} compases</span></div>
                <div className="stems">
                  {song.stems.map((st) => <span key={st.label} className={`stem r-${st.role}`}>{st.label}</span>)}
                </div>
              </div>
            ) : <div className="empty-keys">{songs?.length === 0 ? "La biblioteca está vacía" : "Cargando…"}</div>}
          </RackUnit>
        </Rack>
      </div>
    </>
  );
}
