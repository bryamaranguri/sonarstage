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
  setlist?: { number: number; title: string; sections: string[] }[];
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
  key: string | null;
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
