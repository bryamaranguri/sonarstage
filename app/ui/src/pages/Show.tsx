import { useEffect, useState } from "react";
import { api, Band, fmtSemis, fmtTime, Job, ShowInfo, SongSummary } from "../api";
import { Lcd, Led, Rack, RackUnit, Screw, Toggle } from "../components/hardware";

type Pick = { folder: string; title: string; semitones: number };

function todayName() {
  const d = new Date();
  const days = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
  return `${days[d.getDay()]} ${d.getDate()}-${d.getMonth() + 1}`;
}

export default function ShowPage() {
  const [songs, setSongs] = useState<SongSummary[]>([]);
  const [bands, setBands] = useState<Band[]>([]);
  const [shows, setShows] = useState<ShowInfo[]>([]);
  const [picks, setPicks] = useState<Pick[]>([]);
  const [name, setName] = useState(todayName);
  const [band, setBand] = useState<string>("");
  const [present, setPresent] = useState<string[] | null>(null);
  const [profile, setProfile] = useState("2");
  const [job, setJob] = useState<Job>();
  const [err, setErr] = useState<string>();

  const refreshShows = () => api.shows().then(setShows).catch(() => {});
  useEffect(() => {
    api.library().then(setSongs).catch((e) => setErr(e.message));
    api.bands().then((b) => { setBands(b); if (b[0]) setBand(b[0].id); }).catch(() => {});
    refreshShows();
  }, []);
  useEffect(() => {
    if (!job || job.state !== "running") return;
    const t = window.setTimeout(() => api.job(job.id).then((j) => { setJob(j); if (j.state === "done") refreshShows(); }), 700);
    return () => window.clearTimeout(t);
  }, [job]);

  const theBand = bands.find((b) => b.id === band);
  const add = (s: SongSummary) => setPicks((p) => [...p, { folder: s.folder, title: s.title, semitones: 0 }]);
  const move = (i: number, d: number) => setPicks((p) => {
    const j = i + d;
    if (j < 0 || j >= p.length) return p;
    const n = [...p];
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });
  const keysOf = (folder: string) => {
    const s = songs.find((x) => x.folder === folder);
    return [0, ...(s?.prepared ?? []).filter((k) => k !== 0)].sort((a, b) => a - b);
  };
  const cycleKey = (i: number, d: number) => setPicks((p) => p.map((x, k) => {
    if (k !== i) return x;
    const keys = keysOf(x.folder);
    const at = keys.indexOf(x.semitones);
    return { ...x, semitones: keys[Math.max(0, Math.min(keys.length - 1, at + d))] };
  }));
  const totalS = picks.reduce((a, p) => a + (songs.find((s) => s.folder === p.folder)?.durationS ?? 0), 0);
  const isPresent = (id: string) => present === null || present.includes(id);
  const togglePresent = (id: string) => {
    const all = theBand?.musicians.map((m) => m.id) ?? [];
    const cur = present ?? all;
    setPresent(cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  };

  const prepare = async () => {
    setErr(undefined);
    try {
      setJob(await api.prepareShow({ name, songs: picks.map((p) => ({ title: p.title, semitones: p.semitones })),
        band: band || undefined, present: present ?? undefined, profile }));
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <>
      <div className="header-strip">
        <div className="hs-center wide">
          <div className="hs-actions">
            <span className="hs-caption">NOMBRE DEL SHOW</span><span className="spacer" />
            <button className="text-btn" onClick={() => setPicks([])}>VACIAR</button>
            <button className="text-btn strong" onClick={prepare} disabled={!picks.length || job?.state === "running"}>PREPARAR</button>
          </div>
          <label className="preset-select"><input value={name} onChange={(e) => setName(e.target.value)} /></label>
        </div>
        <div className="hs-divider" />
        <div className="hs-toggles">
          <div className="toggle-row">SALIDAS
            <select className="mini" value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="2">2</option><option value="4">4</option>
            </select>
          </div>
          <div className="toggle-row">BANDA
            <select className="mini" value={band} onChange={(e) => { setBand(e.target.value); setPresent(null); }}>
              <option value="">Sin banda</option>
              {bands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
        </div>
      </div>
      {err && <div className="banner warn">{err}</div>}

      <div className="split three">
        <div className="browser">
          <div className="browser-head">BIBLIOTECA</div>
          {songs.map((s) => (
            <button key={s.folder} className="browser-row" onClick={() => add(s)}>
              <span className="br-title">{s.title}</span>
              <span className="br-meta">{s.bpm.toFixed(0)} BPM · {fmtTime(s.durationS)}</span>
              <span className="br-add">＋</span>
            </button>
          ))}
        </div>

        <div className="setlist">
          {picks.length === 0 && <div className="setlist-empty">Agrega canciones desde la biblioteca</div>}
          {picks.map((p, i) => (
            <div key={i} className="cassette">
              <Screw style={{ left: 8, top: "50%", marginTop: -7, width: 14, height: 14 }} />
              <span className="cas-n">{i + 1}</span>
              <span className="cas-title">{p.title}</span>
              <div className="cas-key">
                <button onClick={() => cycleKey(i, -1)} aria-label="Bajar tono">◀</button>
                <span>{fmtSemis(p.semitones)}</span>
                <button onClick={() => cycleKey(i, +1)} aria-label="Subir tono">▶</button>
              </div>
              <div className="cas-move">
                <button onClick={() => move(i, -1)} aria-label="Subir">▲</button>
                <button onClick={() => move(i, +1)} aria-label="Bajar">▼</button>
                <button onClick={() => setPicks((x) => x.filter((_, k) => k !== i))} aria-label="Quitar">✕</button>
              </div>
              <Screw style={{ right: 8, top: "50%", marginTop: -7, width: 14, height: 14 }} />
            </div>
          ))}
          {picks.length > 0 && <div className="setlist-total">{picks.length} canciones · {fmtTime(totalS)} de música</div>}
        </div>

        <Rack>
          <RackUnit title="BANDA" subtitle="Quién toca esta semana" compact>
            <div className="tracks">
              {theBand ? theBand.musicians.map((m) => (
                <div className="track" key={m.id}>
                  <Led on={isPresent(m.id)} />
                  <Toggle on={isPresent(m.id)} top="TOCA" bottom="SECUENCIA" label={m.name} onClick={() => togglePresent(m.id)} />
                  <span className="track-name">{m.name.toUpperCase()}</span>
                </div>
              )) : <div className="empty-keys">Sin banda: todo va en la secuencia</div>}
            </div>
          </RackUnit>
          <RackUnit title="ESTADO" compact>
            <Lcd className="lcd-wide">
              {!job && <div className="lcd-line dim">Elige canciones y tonos, y pulsa PREPARAR.</div>}
              {job?.state === "running" && <div className="lcd-line amber blink-soft">Preparando «{name}»… renderizando audio</div>}
              {job?.state === "error" && <div className="lcd-line red">No se pudo: {job.error}</div>}
              {job?.state === "done" && <>
                <div className="lcd-line ok">Show listo · {job.result.version}</div>
                <div className="lcd-line dim path">{job.result.als}</div>
              </>}
            </Lcd>
          </RackUnit>
          <RackUnit title="SHOWS" subtitle="Preparados en este disco" compact>
            <div className="shows-list">
              {shows.map((s) => (
                <div key={s.name} className="show-row">
                  <Led on={false} />
                  <span className="sr-name">{s.name}</span>
                  <span className="sr-songs">{s.songs.map((x) => x.title + (x.semitones ? ` (${fmtSemis(x.semitones)})` : "")).join(" · ")}</span>
                  <button className="text-btn light" onClick={() => api.openShow(s.name)}>ABRIR</button>
                </div>
              ))}
              {shows.length === 0 && <div className="empty-keys">Todavía no hay shows</div>}
            </div>
          </RackUnit>
        </Rack>
      </div>
    </>
  );
}
