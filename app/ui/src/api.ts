// Talks to the SonarStage engine (python -m sonarstage_import.server) on this Mac.

export type LiveState = {
  playing: boolean;
  beat: number;
  tempo: number;
  song: number | null;
  song_title: string | null;
  section: string | null;
  section_bar: number | null;
  section_bars: number | null;
  loop: boolean;
  pending: string | null;
  landing?: string | null;
  autostop: boolean;
  next_song?: string | null;
  guide_quiet?: boolean;
  jump_mode?: "section" | "bar" | "now";
};

export type Live = {
  ok: boolean;
  error?: string;
  state?: LiveState;
  setlist?: { number: number; title: string; sections: string[]; key?: string | null; keyConfirmed?: boolean; semitones?: number }[];
  order?: number[];
  tracks?: string[];
  mutes?: Record<string, boolean>;
};

export type SongSummary = {
  id: string;
  title: string;
  folder: string;
  bpm: number;
  timeSignature: string;
  key: string | null;          // the confirmed key, else the estimate
  keyConfirmed: boolean;
  keyPending: boolean;         // still being estimated
  prepared: number[];
  sections: number;
  bars: number;
  durationS: number;
  stems: number;
  parts: string[];
  source?: string;
  error?: string;
};

export type Section = { name: string; kind: string; startBar: number; bars: number; guide?: string };
export type Song = { title: string; tempo: { bpm: number }; sections: Section[]; stems: { label: string; role: string }[] };
export type Band = { id: string; name: string; musicians: { id: string; name: string; role: string }[] };
export type ShowInfo = { name: string; songs: { title: string; semitones: number }[]; band?: string; profile?: string; liveVersion?: string };
export type PartsMusician = { id: string; name: string; role?: string; default: string[]; stems: string[]; matrix: Record<string, string[]> | null };
export type PartsView = { title: string; folder: string; bpm: number; timeSignature: string;
  sections: { name: string; kind?: string; startBar: number; bars: number; pickupBeats: number }[];
  band: { id: string; name: string }; musicians: PartsMusician[] };
export type Job = { id: string; state: "running" | "done" | "error"; error?: string; result?: any };
export type VoiceLine = { n: number; t: number; text: string };
export type Voice = { running: boolean; settings: any; lines: VoiceLine[] };
export type Device = { index: number; name: string; inputs: number; outputs: number; rate: number };
export type Status = { config: Record<string, string | null>; link: { ok: boolean; error?: string }; voice: { running: boolean } };

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch("/api/" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data?.error || r.statusText);
  return data as T;
}

export const api = {
  status: () => call<Status>("GET", "status"),
  library: () => call<SongSummary[]>("GET", "library"),
  song: (folder: string) => call<Song>("GET", "library/" + encodeURIComponent(folder)),
  setKey: (folder: string, key: string) => call<SongSummary>("POST", "library/" + encodeURIComponent(folder) + "/key", { key }),
  bands: () => call<Band[]>("GET", "bands"),
  shows: () => call<ShowInfo[]>("GET", "shows"),
  prepareShow: (body: unknown) => call<Job>("POST", "shows", body),
  openShow: (name: string) => call<{ opened: string }>("POST", "shows/" + encodeURIComponent(name) + "/open"),
  job: (id: string) => call<Job>("GET", "jobs/" + id),
  live: () => call<Live>("GET", "live"),
  cmd: (msg: Record<string, unknown>) => call<{ ok: boolean; error?: string; state?: LiveState }>("POST", "live", msg),
  voice: (since: number) => call<Voice>("GET", "voice?since=" + since),
  voiceStart: (body: unknown) => call<Voice>("POST", "voice/start", body),
  voiceStop: () => call<Voice>("POST", "voice/stop"),
  devices: () => call<Device[]>("GET", "devices"),
  parts: (folder: string, band: string) => call<PartsView>("GET", `parts/${encodeURIComponent(folder)}?band=${encodeURIComponent(band)}`),
  setParts: (folder: string, band: string, musician: string, matrix: Record<string, string[]> | null) =>
    call<PartsView>("POST", `parts/${encodeURIComponent(folder)}`, { band, musician, matrix }),
  setPickup: (folder: string, section: number, beats: number) => call<{ ok: boolean }>("POST", `parts/${encodeURIComponent(folder)}/pickup`, { section, beats }),
  activity: (folder: string) => call<{ ready: boolean; levels?: Record<string, number[]>; error?: string }>("GET", `parts/${encodeURIComponent(folder)}/activity`),
};

/** Re-run `fn` every `ms` while mounted (polling the engine is enough on one Mac). */
import { useEffect, useRef, useState } from "react";
export function usePoll<T>(fn: () => Promise<T>, ms: number): [T | undefined, string | undefined] {
  const [data, setData] = useState<T>();
  const [err, setErr] = useState<string>();
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    let timer: number;
    const tick = async () => {
      try {
        const d = await fnRef.current();
        if (alive) { setData(d); setErr(undefined); }
      } catch (e: any) {
        if (alive) setErr(e.message || String(e));
      }
      if (alive) timer = window.setTimeout(tick, ms);
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [ms]);
  return [data, err];
}

export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
export const fmtSemis = (n: number) => (n === 0 ? "Original" : (n > 0 ? "+" : "") + n);

// keys as musicians write them (same spelling as the engine's musickey.py)
export const MAJOR_KEYS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
export const MINOR_KEYS = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"];

/** "G", +2 → "A"; unknown key → null. */
export function keyAt(key: string | null | undefined, semitones: number): string | null {
  if (!key) return null;
  const minor = key.endsWith("m");
  const list = minor ? MINOR_KEYS : MAJOR_KEYS;
  const i = list.indexOf(key);
  return i < 0 ? null : list[(((i + semitones) % 12) + 12) % 12];
}

/** "A (+2)", "G", or the offset alone when the key is unknown. */
export const fmtKey = (key: string | null | undefined, semitones: number) => {
  const k = keyAt(key, semitones);
  if (!k) return fmtSemis(semitones);
  return semitones ? `${k} (${semitones > 0 ? "+" : ""}${semitones})` : k;
};
