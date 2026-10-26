import { useEffect, useMemo, useState } from "react";
import { api, Band, PartsMusician, PartsView, SongSummary } from "../api";
import { FlatKnob, Lcd, Lever, ModeSelector, Rack, RackUnit } from "../components/hardware";

type Zoom = "22" | "30" | "42";
type Matrix = Record<string, string[]>;

/** The matrix a musician plays now: their own, or their default stems in every section. */
function effective(m: PartsMusician, starts: number[]): Matrix {
  if (m.matrix) return m.matrix;
  const def = m.default.filter((d) => m.stems.some((s) => s.toLowerCase() === d.toLowerCase()));
  return Object.fromEntries(starts.map((b) => [String(b), def]));
}

/** How loud a stem is in a section, 0 (silent) … 1 (its loudest), like the CLI grid. */
function level(levels: number[] | undefined, i: number) {
  if (!levels) return 0.5;
  const loudest = Math.max(...levels);
  const v = levels[i];
  if (v < -60 || v < loudest - 30) return 0;
  return Math.max(0.18, Math.min(1, (v - (loudest - 30)) / 30));
}

export default function MatrixPage() {
  const [songs, setSongs] = useState<SongSummary[]>([]);
  const [bands, setBands] = useState<Band[]>([]);
  const [folder, setFolder] = useState<string>();
  const [bandId, setBandId] = useState<string>();
  const [view, setView] = useState<PartsView>();
  const [who, setWho] = useState<string>();
  const [levels, setLevels] = useState<Record<string, number[]>>();
  const [sel, setSel] = useState<number>(2);
  const [zoom, setZoom] = useState<Zoom>("30");
  const [err, setErr] = useState<string>();

  useEffect(() => {
    api.library().then((s) => { setSongs(s); setFolder((f) => f ?? s[0]?.folder); }).catch((e) => setErr(e.message));
    api.bands().then((b) => { setBands(b); setBandId((x) => x ?? b[0]?.id); }).catch((e) => setErr(e.message));
  }, []);
  useEffect(() => {
    if (!folder || !bandId) return;
    setView(undefined);
    api.parts(folder, bandId).then((v) => { setView(v); setWho((w) => (v.musicians.some((m) => m.id === w) ? w : v.musicians.find((m) => m.stems.length > 1)?.id ?? v.musicians[0]?.id)); setErr(undefined); })
      .catch((e) => setErr(e.message));
  }, [folder, bandId]);
  useEffect(() => {
    if (!folder) return;
    setLevels(undefined);
    let alive = true;
    const poll = async () => {
      try {
        const r = await api.activity(folder);
        if (!alive) return;
        if (r.ready) setLevels(r.levels);
        else if (!r.error) window.setTimeout(poll, 800);
      } catch { /* keep the matrix usable without levels */ }
    };
    poll();
    return () => { alive = false; };
  }, [folder]);

  const m = view?.musicians.find((x) => x.id === who);
  const starts = view?.sections.map((s) => s.startBar) ?? [];
  const matrix = m && view ? effective(m, starts) : {};
  const px = Number(zoom);
  const total = view ? view.sections.reduce((a, s) => Math.max(a, s.startBar + s.bars - 1), 0) : 0;
  const songIdx = songs.findIndex((s) => s.folder === folder);

  const save = async (next: Matrix | null) => {
    if (!folder || !bandId || !m) return;
    try {
      setView(await api.setParts(folder, bandId, m.id, next));
      setErr(undefined);
    } catch (e: any) {
      setErr(e.message);
    }
  };
  const toggle = (bar: number, stem: string) => {
    const next: Matrix = Object.fromEntries(Object.entries(matrix).map(([k, v]) => [k, [...v]]));
    const cur = next[String(bar)] ?? [];
    next[String(bar)] = cur.includes(stem) ? cur.filter((x) => x !== stem) : [...cur, stem];
    save(next);
  };
  const summary = useMemo(() => {
    if (!m || !view) return { live: [] as string[], seq: [] as string[] };
    const live = m.stems.map((st) => [st, view.sections.filter((s) => (matrix[String(s.startBar)] ?? []).includes(st)).length] as const)
      .filter(([, n]) => n > 0).map(([st, n]) => `${st} (${n})`);
    const seq = m.stems.filter((st) => !view.sections.some((s) => (matrix[String(s.startBar)] ?? []).includes(st)));
    return { live, seq };
  }, [m, view, matrix]);
  const section = view?.sections[sel - 1];

  return (
    <>
      <div className="header-strip">
        <FlatKnob label="STEMS" value={(m?.stems.length ?? 0) / 8} text={String(m?.stems.length ?? "—")} />
        <FlatKnob label="SECCIONES" value={(view?.sections.length ?? 0) / 32} text={String(view?.sections.length ?? "—")} />
        <div className="hs-divider" />
        <div className="hs-center">
          <div className="hs-actions">
            <button className="arrow" onClick={() => songIdx > 0 && setFolder(songs[songIdx - 1].folder)} aria-label="Canción anterior">←</button>
            <span className="vsep" />
            <button className="arrow" onClick={() => songIdx < songs.length - 1 && setFolder(songs[songIdx + 1].folder)} aria-label="Canción siguiente">→</button>
            <span className="spacer" />
            <button className="text-btn" onClick={() => save(null)} title="Sus stems de siempre en toda la canción">LO HABITUAL</button>
            <button className="text-btn" onClick={() => save({})} title="No toca nada: todo a la secuencia">VACIAR</button>
          </div>
          <label className="preset-select">
            <select value={folder ?? ""} onChange={(e) => setFolder(e.target.value)}>
              {songs.map((s) => <option key={s.folder} value={s.folder}>{s.title}</option>)}
            </select>
            <span className="chev">⌄</span>
          </label>
        </div>
        <div className="hs-divider" />
        <div className="hs-toggles">
          <div className="toggle-row">BANDA
            <select className="mini" value={bandId ?? ""} onChange={(e) => setBandId(e.target.value)}>
              {bands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <Lever label="ZOOM" value={zoom} onChange={setZoom}
            options={[{ id: "22", label: "LEJOS" }, { id: "30", label: "MEDIO" }, { id: "42", label: "CERCA" }]} />
        </div>
      </div>
      {err && <div className="banner warn" onClick={() => setErr(undefined)}>{err}</div>}
      {!bands.length && <div className="banner">Primero crea una banda (material/biblioteca/_bandas).</div>}

      <div className="split">
        <div className="browser">
          <div className="browser-head">MÚSICOS · {view?.band.name ?? ""}</div>
          {view?.musicians.map((x) => {
            const own = !!x.matrix;
            return (
              <button key={x.id} className={`browser-row ${x.id === who ? "sel" : ""}`} onClick={() => setWho(x.id)}>
                <span className="br-title">{x.name}</span>
                <span className="br-meta">{x.stems.length ? `${x.stems.join(" · ")}${own ? " · por sección" : " · lo habitual"}` : "la canción no tiene sus stems"}</span>
              </button>
            );
          })}
        </div>
        <Rack>
          <RackUnit title="MATRIZ" subtitle={m ? `${m.name} · ${view?.title}` : view?.title}>
            {view && m ? (
              <div className="matrix">
                <Lcd className="lcd-wide">
                  <div className="lcd-row"><span className="lcd-key">EN VIVO · LO TOCA {m.name.toUpperCase()}</span><span className="lcd-key">SIGUE EN LA SECUENCIA</span></div>
                  <div className="lcd-row"><span className="live-text">{summary.live.join(" · ") || "nada"}</span>
                    <span className="amber">{summary.seq.join(" · ") || "—"}</span></div>
                  {!levels && <div className="lcd-line dim">Midiendo cuánto suena cada stem…</div>}
                </Lcd>
                {m.stems.length === 0 ? <div className="empty-keys">La canción no tiene stems de {m.name}.</div> : (
                  <div className="timeline-scroll">
                    <div className="tl-grid" style={{ width: 92 + total * px }}>
                      <div className="tl-ruler-row">
                        <span className="tl-head" />
                        <div className="tl-track">
                          {Array.from({ length: Math.ceil(total / 4) }, (_, i) => (
                            <span key={i} className="tl-tick" style={{ left: i * 4 * px }}>{i * 4 + 1}</span>
                          ))}
                        </div>
                      </div>
                      <div className="tl-sections">
                        <span className="tl-head">SECCIÓN</span>
                        <div className="tl-track">
                          {view.sections.map((s, i) => (
                            <button key={i} className={`tl-sec ${sel === i + 1 ? "sel" : ""}`} onClick={() => setSel(i + 1)}
                              style={{ left: (s.startBar - 1) * px, width: s.bars * px }} title={`${s.name} · compases ${s.startBar}–${s.startBar + s.bars - 1}`}>
                              {s.pickupBeats > 0 && <i className="pickup" />}
                              <span>{s.name}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                      {m.stems.map((st) => (
                        <div className="tl-stem" key={st}>
                          <span className="tl-head">{st}</span>
                          <div className="tl-track">
                            {view.sections.map((s, i) => {
                              const on = (matrix[String(s.startBar)] ?? []).includes(st);
                              const lv = level(levels?.[st], i);
                              return (
                                <button key={i} className={`clip ${on ? "live" : lv ? "seq" : "silent"} ${sel === i + 1 ? "sel" : ""}`}
                                  style={{ left: (s.startBar - 1) * px, width: s.bars * px }}
                                  onClick={() => toggle(s.startBar, st)}
                                  title={`${st} · ${s.name}: ${on ? "lo toca" : lv ? "va en la secuencia" : "no suena"}`}>
                                  <span style={{ height: `${Math.max(on ? 0.3 : 0, lv) * 100}%` }} />
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="legend">
                  <span><i className="sw live" />lo toca el músico (EN VIVO)</span>
                  <span><i className="sw seq" />suena y va a la SECUENCIA</span>
                  <span><i className="sw silent" />no suena</span>
                  <span className="dim">La altura es cuánto suena el stem en esa sección.</span>
                </div>
              </div>
            ) : <div className="empty-keys">{err ? "—" : "Cargando…"}</div>}
          </RackUnit>
          {section && view && (
            <RackUnit title={`SECCIÓN ${sel}`} subtitle={`${section.name} · compases ${section.startBar}–${section.startBar + section.bars - 1}`} compact>
              <div className="section-panel">
                <ModeSelector title="ANACRUSA" value={String(section.pickupBeats) as "0" | "1" | "2" | "3"}
                  options={[{ id: "0", label: "NO" }, { id: "1", label: "1 T" }, { id: "2", label: "2 T" }, { id: "3", label: "3 T" }]}
                  onChange={async (b) => {
                    if (sel < 2) { setErr("La primera sección no lleva anacrusa."); return; }
                    try { await api.setPickup(view.folder, sel, Number(b)); setView(await api.parts(view.folder, view.band.id)); } catch (e: any) { setErr(e.message); }
                  }} />
                <p className="hint-text">Anacrusa: la sección empieza esos tiempos antes de su compás 1, para que las notas que entran
                  a ella sean de quien la toca. Es poco frecuente; en la línea de tiempo se marca con una muesca ámbar.</p>
              </div>
            </RackUnit>
          )}
        </Rack>
      </div>
    </>
  );
}
