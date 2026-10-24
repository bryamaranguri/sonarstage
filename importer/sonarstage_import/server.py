"""SonarStage engine: a local HTTP server (only this Mac) between the app and everything else.

    python -m sonarstage_import.server --material ~/Ing/01-proj/sonar-stage/material [--port 11011]

JSON API under /api (see ROUTES); anything else is the app's built UI (app/ui/dist), so
`http://127.0.0.1:11011` is the app in a browser while there is no desktop shell yet.
Long jobs (prepare a show) run in a thread and are polled at /api/jobs/<id>. The voice
listener runs in a thread too, and its lines are kept for the live screen.
"""
import argparse
import json
import mimetypes
import re
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import link_client

HOST, PORT = "127.0.0.1", 11011
UI_DIR = Path(__file__).resolve().parents[2] / "app" / "ui" / "dist"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Config(object):
    """Where things are. Everything lives under the material folder unless said otherwise."""

    def __init__(self, material, template=None, library=None, shows=None, models=None, voices=None):
        m = Path(material).expanduser()
        self.material = m
        self.library = Path(library) if library else m / "biblioteca"
        self.shows = Path(shows) if shows else m / "shows"
        self.models = Path(models) if models else m / "modelos"
        self.voices = Path(voices) if voices else m / "voces"
        self.template = Path(template) if template else next(iter(sorted(m.glob("* Project/*.als"))), None)

    def public(self):
        return {k: str(v) if v else None for k, v in vars(self).items()}


# --- library ------------------------------------------------------------------------------

def song_summary(song_dir):
    song = json.loads((song_dir / "cancion.json").read_text())
    bpb = int(song["tempo"]["timeSignature"].split("/")[0])
    last = song["sections"][-1] if song["sections"] else None
    bars = (last["startBar"] + last["bars"] - 1) if last else 0
    return {"id": song["id"], "title": song["title"], "folder": song_dir.name, "bpm": song["tempo"]["bpm"],
            "timeSignature": song["tempo"]["timeSignature"], "key": song["key"].get("original"),
            "prepared": song["key"].get("prepared", [0]), "sections": len(song["sections"]),
            "bars": bars, "durationS": round(bars * bpb * 60 / song["tempo"]["bpm"], 1),
            "stems": len(song["stems"]), "parts": sorted(song.get("parts", {})),
            "source": song.get("source", {}).get("name") if isinstance(song.get("source"), dict) else song.get("source")}


def list_library(cfg):
    if not cfg.library.is_dir():
        return []
    out = []
    for d in sorted(cfg.library.iterdir()):
        if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "cancion.json").exists():
            try:
                out.append(song_summary(d))
            except Exception as e:                       # a broken song must not hide the others
                out.append({"folder": d.name, "title": d.name, "error": str(e)})
    return out


def song_dir(cfg, folder):
    d = (cfg.library / folder).resolve()
    if cfg.library.resolve() not in d.parents or not (d / "cancion.json").exists():
        raise ApiError(404, "No está en la biblioteca: %s" % folder)
    return d


def list_bands(cfg):
    folder = cfg.library / "_bandas"
    return [json.loads(f.read_text()) for f in sorted(folder.glob("*.json"))] if folder.is_dir() else []


def list_shows(cfg):
    out = []
    if cfg.shows.is_dir():
        for d in sorted(cfg.shows.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            meta = d / "show.json"
            if d.is_dir() and meta.exists():
                info = json.loads(meta.read_text())
                out.append({"name": d.name, "songs": [{"title": s["title"], "semitones": s["semitones"]}
                                                      for s in info.get("songs", [])],
                            "band": info.get("band"), "profile": info.get("profile"),
                            "liveVersion": info.get("live_version"), "als": str(d / info.get("als", ""))})
    return out


# --- jobs -----------------------------------------------------------------------------------

class Jobs(object):
    def __init__(self):
        self.jobs, self.lock = {}, threading.Lock()

    def start(self, kind, fn):
        job = {"id": uuid.uuid4().hex[:8], "kind": kind, "state": "running", "started": time.time(),
               "result": None, "error": None}
        with self.lock:
            self.jobs[job["id"]] = job

        def run():
            try:
                job["result"] = fn()
                job["state"] = "done"
            except Exception as e:
                job["error"], job["state"] = str(e), "error"
                traceback.print_exc()
            job["ended"] = time.time()
        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            raise ApiError(404, "No hay un trabajo %s" % job_id)
        return job


def prepare_show_job(cfg, body):
    from . import parts
    from .show import prepare_show
    name = (body.get("name") or "").strip()
    if not name or "/" in name or name.startswith("."):
        raise ApiError(400, "El show necesita un nombre válido")
    songs = body.get("songs") or []
    if not songs:
        raise ApiError(400, "El show no tiene canciones")
    out = cfg.shows / name
    if out.exists() and any(out.iterdir()):
        raise ApiError(409, "Ya existe un show llamado «%s»" % name)
    if cfg.template is None or not cfg.template.exists():
        raise ApiError(400, "Falta la plantilla de Ableton")
    specs = ["%s:%d" % (s["title"], int(s.get("semitones", 0))) for s in songs]
    band = None
    if body.get("band"):
        path = cfg.library / "_bandas" / ("%s.json" % body["band"])
        band = parts.load_band(path)
    present = body.get("present")

    def run():
        result, report = prepare_show(cfg.library, out, cfg.template, specs, band, present,
                                      body.get("profile", "2"), float(body.get("gap", 30)),
                                      int(body.get("sampleRate", 48000)))
        return {"als": str(result["als"]), "version": result["version"], "songs": report,
                "tracks": ["%s/%s" % t for t in result["tracks"]]}
    return run


# --- voice ----------------------------------------------------------------------------------

class Voice(object):
    """The voice listener in a thread; its lines are kept for the live screen."""

    def __init__(self, cfg, send=link_client.send):
        self.cfg, self.send = cfg, send
        self.lines = deque(maxlen=200)
        self.thread, self.stop_event, self.settings = None, None, None
        self.seq = 0

    def out(self, text):
        self.seq += 1
        self.lines.append({"n": self.seq, "t": time.time(), "text": text})

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, device, channel=1, confirm_channel=2, dry_run=False, wake=None):
        if self.running():
            raise ApiError(409, "La voz ya está escuchando")
        from .voice import AudioIO, Confirmer, Context, VoskTranscriber, WAKE_WORDS, listen
        transcribe = VoskTranscriber(self.cfg.models)
        has_voices = self.cfg.voices.is_dir() and any(self.cfg.voices.glob("*.wav"))
        audio = AudioIO(device, int(channel), int(confirm_channel) if has_voices else None, out=self.out)
        confirm = None
        if audio.open() and has_voices:
            confirm = Confirmer(self.cfg.voices, audio.sr, audio.play)
        self.stop_event = threading.Event()
        self.settings = {"device": device, "channel": channel, "confirmChannel": confirm_channel if confirm else None,
                         "rate": audio.sr, "dryRun": dry_run}
        wake_words = tuple(wake) if wake else WAKE_WORDS
        stop = self.stop_event

        def run():
            self.out("Escuchando: di «%s, …»" % "» o «".join(w.capitalize() for w in wake_words))
            try:
                listen(audio.blocks(stop), audio.sr, transcribe, Context.from_link, wake_words, dry_run,
                       send=self.send, out=self.out, confirm=confirm)
            except Exception as e:
                self.out("⚠ La voz se detuvo: %s" % e)
            finally:
                audio.close()
                self.out("Voz detenida.")
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self.status()

    def stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)
        return self.status()

    def status(self, since=0):
        return {"running": self.running(), "settings": self.settings if self.running() else None,
                "lines": [l for l in self.lines if l["n"] > since]}


# --- HTTP -----------------------------------------------------------------------------------

class Engine(object):
    def __init__(self, cfg, send=link_client.send):
        self.cfg, self.send = cfg, send
        self.jobs = Jobs()
        self.voice = Voice(cfg, send)

    def route(self, method, path, query, body):
        parts = [unquote(p) for p in path.strip("/").split("/")][1:]          # after "api"
        key = (method, parts[0] if parts else "")
        if key == ("GET", "status"):
            link = self.send({"cmd": "status"})
            return {"config": self.cfg.public(), "link": {"ok": bool(link.get("ok")), "error": link.get("error")},
                    "voice": {"running": self.voice.running()}}
        if key == ("GET", "library"):
            if len(parts) == 1:
                return list_library(self.cfg)
            return json.loads((song_dir(self.cfg, parts[1]) / "cancion.json").read_text())
        if key == ("GET", "bands"):
            return list_bands(self.cfg)
        if key == ("GET", "shows"):
            return list_shows(self.cfg)
        if key == ("POST", "shows"):
            if len(parts) == 3 and parts[2] == "open":
                return self.open_show(parts[1])
            job = self.jobs.start("show", prepare_show_job(self.cfg, body))
            return job
        if key == ("GET", "jobs") and len(parts) == 2:
            return self.jobs.get(parts[1])
        if key == ("GET", "live"):
            r = self.send({"cmd": "setlist"})
            return {"ok": bool(r.get("ok")), "error": r.get("error"), "state": r.get("state"),
                    "setlist": r.get("setlist"), "order": r.get("order"), "tracks": r.get("tracks")}
        if key == ("POST", "live"):
            if not isinstance(body, dict) or "cmd" not in body:
                raise ApiError(400, "Falta el comando")
            return self.send(body)
        if key == ("GET", "devices"):
            from .voice import input_devices
            return input_devices()
        if key == ("GET", "voice"):
            return self.voice.status(int(query.get("since", 0)))
        if key == ("POST", "voice"):
            action = parts[1] if len(parts) > 1 else ""
            if action == "start":
                return self.voice.start(body.get("device"), body.get("channel", 1), body.get("confirmChannel", 2),
                                        bool(body.get("dryRun")), body.get("wake"))
            if action == "stop":
                return self.voice.stop()
        raise ApiError(404, "No existe %s %s" % (method, path))

    def open_show(self, name):
        import subprocess
        show = next((s for s in list_shows(self.cfg) if s["name"] == name), None)
        if show is None:
            raise ApiError(404, "No hay un show «%s»" % name)
        if sys.platform == "darwin":
            subprocess.Popen(["open", show["als"]])
        return {"opened": show["als"]}


def make_handler(engine, ui_dir=UI_DIR):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SonarStage"

        def log_message(self, fmt, *args):            # quiet: the app polls a lot
            pass

        def _json(self, status, data):
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _api(self, method):
            url = urlparse(self.path)
            query = dict(q.split("=", 1) for q in url.query.split("&") if "=" in q)
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    try:
                        body = json.loads(self.rfile.read(n).decode("utf-8"))
                    except ValueError:
                        return self._json(400, {"error": "JSON inválido"})
            try:
                self._json(200, engine.route(method, url.path, query, body))
            except ApiError as e:
                self._json(e.status, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})

        def _static(self):
            path = urlparse(self.path).path
            target = (ui_dir / path.lstrip("/")).resolve() if path != "/" else ui_dir / "index.html"
            if not target.is_file() or ui_dir.resolve() not in target.resolve().parents:
                target = ui_dir / "index.html"                    # single-page app
            if not target.is_file():
                raw = b"SonarStage: falta construir la app (cd app/ui && npm run build)."
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                return self.wfile.write(raw)
            raw = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._api("GET")
            return self._static()

        def do_POST(self):
            if self.path.startswith("/api/"):
                return self._api("POST")
            self._json(404, {"error": "no"})
    return Handler


def serve(cfg, host=HOST, port=PORT, ui_dir=UI_DIR):
    engine = Engine(cfg)
    httpd = ThreadingHTTPServer((host, port), make_handler(engine, ui_dir))
    return engine, httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--material", required=True, help="Carpeta con biblioteca, shows, modelos y voces")
    ap.add_argument("--template", help="Plantilla .als (por defecto, la primera dentro de material)")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    cfg = Config(args.material, args.template)
    _, httpd = serve(cfg, port=args.port)
    print("SonarStage en http://%s:%d  (biblioteca: %s)" % (HOST, args.port, cfg.library), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
