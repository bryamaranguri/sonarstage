"""The engine's HTTP API, over a real socket, with a fake bridge and no audio."""
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sonarstage_import import server

SONG = {"schemaVersion": 1, "id": "alegras", "title": "Alegras mis días", "source": "pack.rar",
        "importedAt": "2026-10-20", "tempo": {"bpm": 128.0, "timeSignature": "4/4", "map": [], "firstDownbeatSec": 0},
        "key": {"original": "?", "prepared": [1]},
        "sections": [{"name": "Cuenta", "kind": "other", "startBar": 1, "bars": 2},
                     {"name": "Coro", "kind": "chorus", "startBar": 3, "bars": 8}],
        "stems": [{"file": "Click.wav", "role": "click", "label": "Click", "harmonic": False, "gainDb": 0,
                   "offsetMs": 0, "monoSafe": True, "sourceFormat": "wav"}], "mix": {}, "notes": ""}


@pytest.fixture
def api(tmp_path):
    lib = tmp_path / "biblioteca"
    (lib / "Alegras mis días").mkdir(parents=True)
    (lib / "Alegras mis días" / "cancion.json").write_text(json.dumps(SONG))
    (lib / "_bandas").mkdir()
    (lib / "_bandas" / "mi-banda.json").write_text(json.dumps({"id": "mi-banda", "name": "Mi banda", "musicians": []}))
    (tmp_path / "plantilla Project").mkdir()
    (tmp_path / "plantilla Project" / "plantilla.als").write_bytes(b"x")
    sent = []

    def send(msg):
        sent.append(msg)
        if msg["cmd"] == "setlist":
            return {"ok": True, "state": {"song": 1, "section": "Coro"}, "setlist": [{"number": 1, "title": "Alegras mis días",
                    "sections": ["Coro"]}], "order": [1], "tracks": ["Click"]}
        return {"ok": True, "state": {"playing": msg["cmd"] == "play"}}

    cfg = server.Config(tmp_path)
    engine = server.Engine(cfg, send=send)
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<!doctype html><title>SonarStage</title>")
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(engine, ui))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"null") if r.headers.get_content_type() == "application/json" else r.read()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    yield call, engine, sent, tmp_path
    httpd.shutdown()


def test_status_and_library(api):
    call, engine, sent, tmp = api
    status, data = call("GET", "/api/status")
    assert status == 200 and data["link"]["ok"] and data["config"]["template"].endswith("plantilla.als")
    status, songs = call("GET", "/api/library")
    assert songs[0]["title"] == "Alegras mis días" and songs[0]["bars"] == 10 and songs[0]["prepared"] == [1]
    assert songs[0]["durationS"] == pytest.approx(10 * 4 * 60 / 128, abs=0.1)
    status, song = call("GET", "/api/library/Alegras%20mis%20d%C3%ADas")
    assert song["sections"][1]["name"] == "Coro"
    assert call("GET", "/api/library/..%2F..%2Fetc")[0] == 404
    assert call("GET", "/api/bands")[1][0]["id"] == "mi-banda"


def test_live_is_the_bridge(api):
    call, engine, sent, tmp = api
    live = call("GET", "/api/live")[1]
    assert live["ok"] and live["setlist"][0]["sections"] == ["Coro"]
    assert call("POST", "/api/live", {"cmd": "play"})[1]["state"]["playing"]
    assert sent[-1] == {"cmd": "play"}
    assert call("POST", "/api/live", {"nope": 1})[0] == 400


def test_prepare_show_runs_as_a_job(api, monkeypatch):
    call, engine, sent, tmp = api
    seen = {}

    def fake_prepare(library, out, template, specs, band, present, profile, gap, sr):
        seen.update(specs=specs, profile=profile, band=band and band["id"])
        out.mkdir(parents=True)
        (out / "show.json").write_text(json.dumps({"songs": [{"title": "Alegras mis días", "semitones": 1}],
                                                   "als": out.name + ".als", "band": "mi-banda", "profile": profile}))
        time.sleep(0.2)
        return {"als": out / (out.name + ".als"), "version": "Ableton Live 12.4.3", "tracks": [("CUES", "Click")]}, []
    monkeypatch.setattr("sonarstage_import.show.prepare_show", fake_prepare)
    monkeypatch.setattr("sonarstage_import.parts.load_band", lambda p: json.loads(Path(p).read_text()))
    status, job = call("POST", "/api/shows", {"name": "Domingo", "songs": [{"title": "Alegras mis días", "semitones": 1}],
                                             "band": "mi-banda", "profile": "2"})
    assert status == 200 and job["state"] == "running"
    for _ in range(50):
        job = call("GET", "/api/jobs/" + job["id"])[1]
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done" and job["result"]["version"] == "Ableton Live 12.4.3"
    assert seen == {"specs": ["Alegras mis días:1"], "profile": "2", "band": "mi-banda"}
    shows = call("GET", "/api/shows")[1]
    assert shows[0]["name"] == "Domingo" and shows[0]["songs"][0]["semitones"] == 1
    assert call("POST", "/api/shows", {"name": "Domingo", "songs": [{"title": "x"}]})[0] == 409
    assert call("POST", "/api/shows", {"name": "", "songs": []})[0] == 400


def test_voice_status_and_the_app_page(api):
    call, engine, sent, tmp = api
    assert call("GET", "/api/voice")[1] == {"running": False, "settings": None, "lines": []}
    engine.voice.out("hola")
    assert [l["text"] for l in call("GET", "/api/voice?since=0")[1]["lines"]] == ["hola"]
    assert call("GET", "/api/voice?since=1")[1]["lines"] == []
    status, page = call("GET", "/biblioteca")                  # any page is the single-page app
    assert status == 200 and b"SonarStage" in page
    assert call("GET", "/api/nada")[0] == 404


def test_parts_matrix_over_the_api(api, monkeypatch):
    call, engine, sent, tmp = api
    song = json.loads((tmp / "biblioteca" / "Alegras mis días" / "cancion.json").read_text())
    song["stems"] += [{"file": f"EG {n}.wav", "role": "eg", "label": f"EG {n}", "harmonic": True, "gainDb": 0,
                       "offsetMs": 0, "monoSafe": True, "sourceFormat": "wav"} for n in (1, 2)]
    (tmp / "biblioteca" / "Alegras mis días" / "cancion.json").write_text(json.dumps(song))
    (tmp / "biblioteca" / "_bandas" / "mi-banda.json").write_text(json.dumps(
        {"schemaVersion": 1, "id": "mi-banda", "name": "Mi banda",
         "musicians": [{"id": "guitarra", "name": "Guitarra", "role": "eg", "default": ["EG 1"]}]}))
    path = "/api/parts/Alegras%20mis%20d%C3%ADas"
    view = call("GET", path + "?band=mi-banda")[1]
    g = view["musicians"][0]
    assert g["stems"] == ["EG 1", "EG 2"] and g["matrix"] is None and view["sections"][1]["startBar"] == 3
    status, view = call("POST", path, {"band": "mi-banda", "musician": "guitarra", "matrix": {"3": ["EG 2"]}})
    assert status == 200 and view["musicians"][0]["matrix"] == {"3": ["EG 2"]}
    assert call("POST", path, {"band": "mi-banda", "musician": "guitarra", "matrix": {"5": ["EG 2"]}})[0] == 400
    view = call("POST", path, {"band": "mi-banda", "musician": "guitarra", "matrix": None})[1]
    assert view["musicians"][0]["matrix"] is None                       # back to the default
    assert call("POST", path + "/pickup", {"section": 2, "beats": 1})[1]["ok"]
    assert call("GET", path + "?band=mi-banda")[1]["sections"][1]["pickupBeats"] == 1

    monkeypatch.setattr("sonarstage_import.parts.activity_cached", lambda d, s: {"EG 1": [-80.0, -12.0]})
    for _ in range(40):
        r = call("GET", path + "/activity")[1]
        if r["ready"]:
            break
        time.sleep(0.05)
    assert r == {"ready": True, "levels": {"EG 1": [-80.0, -12.0]}}
