"""A pretend Ableton for the app, with the real bridge logic (SonarStage Link's LinkCore):
the library's songs one after the other, a transport that plays in real time, guide and
live tracks. `python -m sonarstage_import.server --material … --demo` uses it instead of
Ableton, to try the app anywhere."""
import json
import sys
import threading
import time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2] / "bridge"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))
from SonarStageLink.core import LinkCore  # noqa: E402


class _Cue(object):
    def __init__(self, song, name, time_):
        self.song, self.name, self.time = song, name, time_

    def jump(self):
        if not self.song.is_playing:
            self.song.current_song_time = self.song.start_time = self.time
        else:
            self.song.queued_jump = self.time


class _Track(object):
    def __init__(self, name):
        self.name, self.mute = name, False


class DemoSong(object):
    """Enough of Live's Song for LinkCore, advancing with the clock."""

    def __init__(self, cues, tempo):
        self.signature_numerator, self.tempo = 4, tempo
        self.is_playing, self.current_song_time, self.start_time = False, 0.0, 0.0
        self.loop, self.loop_start, self.loop_length = False, 0.0, 16.0
        self.cue_points = [_Cue(self, n, t) for n, t in cues]
        self.tracks = [_Track(n) for n in ("Click", "Guía", "Batería", "Bajo", "Guitarra eléctrica", "Secuencia")]
        self.clip_trigger_quantization = None
        self.queued_jump = None

    def start_playing(self):
        self.current_song_time = self.start_time
        self.is_playing = True

    def continue_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False

    def advance(self, seconds):
        if not self.is_playing:
            return
        old = self.current_song_time
        new = old + seconds * self.tempo / 60.0
        if self.queued_jump is not None:
            next_bar = (int(old // 4 + 1e-9) + 1) * 4
            if new >= next_bar:
                new, self.queued_jump = self.queued_jump + (new - next_bar), None
        if self.loop and old < self.loop_start + self.loop_length <= new:
            new = self.loop_start + (new - (self.loop_start + self.loop_length))
        self.current_song_time = new


def cues_from_library(library, titles=None):
    cues, start, tempo = [], 0.0, 120.0
    dirs = [d for d in sorted(Path(library).iterdir()) if (d / "cancion.json").exists()]
    if titles:
        dirs = [Path(library) / t for t in titles]
    for n, d in enumerate(dirs, 1):
        song = json.loads((d / "cancion.json").read_text())
        tempo = song["tempo"]["bpm"] if n == 1 else tempo
        for i, sec in enumerate(song["sections"]):
            name = "%d. %s" % (n, song["title"]) if i == 0 else sec["name"]
            cues.append((name, start + (sec["startBar"] - 1) * 4))
        last = song["sections"][-1]
        start += (last["startBar"] + last["bars"] - 1) * 4 + 16
    return cues, tempo


class DemoLink(object):
    """send(msg) like link_client.send, backed by LinkCore over DemoSong."""

    def __init__(self, library, titles=None, tick=0.05):
        cues, tempo = cues_from_library(library, titles)
        self.song = DemoSong(cues, tempo)
        self.core = LinkCore(self.song, bar_quantization="q_bar")
        self.core.notify = lambda text: None
        self.lock = threading.Lock()
        self.tick = tick
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        last = time.monotonic()
        while True:
            time.sleep(self.tick)
            now = time.monotonic()
            with self.lock:
                self.song.advance(now - last)
                self.core.tick()
            last = now

    def __call__(self, msg):
        with self.lock:
            return self.core.handle(msg)
