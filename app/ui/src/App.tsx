import { useEffect, useState } from "react";
import { api, Live as LiveData, usePoll } from "./api";
import { Icons } from "./components/hardware";
import LivePage from "./pages/Live";
import LibraryPage from "./pages/Library";
import ShowPage from "./pages/Show";
import SettingsPage from "./pages/Settings";
import MatrixPage from "./pages/Matrix";
import SamplesPage from "./pages/Samples";

type Page = "live" | "library" | "show" | "matrix" | "settings" | "muestras";
const PAGES: { id: Exclude<Page, "muestras">; label: string }[] = [
  { id: "live", label: "En vivo" },
  { id: "library", label: "Biblioteca" },
  { id: "show", label: "Show" },
  { id: "matrix", label: "Matriz de partes" },
  { id: "settings", label: "Ajustes" },
];

function readPage(): Page {
  const h = window.location.hash.replace("#", "") as Page;
  return PAGES.some((p) => p.id === h) || h === "muestras" ? h : "live";
}

export default function App() {
  const [page, setPage] = useState<Page>(readPage);
  useEffect(() => {
    const on = () => setPage(readPage());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const [live] = usePoll<LiveData>(api.live, page === "live" ? 150 : 1000);
  const [voice] = usePoll(() => api.voice(1e12), 1500);

  return (
    <div className="app">
      <nav className="topnav" aria-label="Pantallas">
        {PAGES.map((p) => (
          <a key={p.id} href={"#" + p.id} className={page === p.id ? "active" : ""} title={p.label} aria-label={p.label}>
            {Icons[p.id]}
            <span className="dot" />
          </a>
        ))}
      </nav>
      <main className="page">
        {page === "live" && <LivePage live={live} />}
        {page === "library" && <LibraryPage />}
        {page === "show" && <ShowPage />}
        {page === "matrix" && <MatrixPage />}
        {page === "settings" && <SettingsPage />}
        {page === "muestras" && <SamplesPage />}
      </main>
      <footer className="statusbar">
        <span className={live?.ok ? "ok" : "bad"}><i />ABLETON</span>
        <span className="sep" />
        <span className={voice?.running ? "ok" : ""}><i />VOZ</span>
        <span className="sep" />
        <span>{live?.state ? `${live.state.tempo.toFixed(1)} BPM` : "— BPM"}</span>
        <span className="sep" />
        <span>{live?.state?.song_title ? live.state.song_title.toUpperCase() : "SIN SHOW"}</span>
        <span className="sep" />
        <a href="#settings">AJUSTES</a>
        <span className="brand">SONARSTAGE</span>
      </footer>
    </div>
  );
}
