"""Voice control: the director's dynamic mic -> commands for SonarStage Link.

    python -m sonarstage_import.voice --devices
    python -m sonarstage_import.voice --device "Scarlett" --channel 2 --model-dir <modelos>
    python -m sonarstage_import.voice ... --dry-run          (listens and shows, sends nothing)
    python -m sonarstage_import.voice --file grabacion.wav --song <biblioteca/Canción> --dry-run

Pipeline, all offline: the mic input is cut into utterances by its level (a dynamic mic
close to the mouth is far above the stage bleed), each utterance is transcribed with
Whisper and parsed with a closed vocabulary (voice_commands.py). Commands only count
after the wake word ("Secuencia, ..."). Every command Ableton accepts is shown in Live's
status bar. Timing is not decided here: the bridge quantizes every jump to the end of
the section, so it is enough to say it some beats before.
"""
import argparse
import json
import queue
import sys
import time
from collections import deque
from math import gcd
from pathlib import Path

import numpy as np

from . import link_client
from .voice_commands import WAKE_WORDS, is_wake_only, parse

SR = 16000
ARMED_SECONDS = 4.0      # after a lone "Secuencia", the next phrase within this time is the order
GROUPS = {"EN VIVO", "SECUENCIA", "CUES", "CONTROL"}
# No initial prompt for Whisper: over music it "hears" the prompt itself (measured: section
# names and "Siguiente" came out of a song with no speech). The words are common Spanish.


class Segmenter(object):
    """Cuts a stream into utterances by level, against an adaptive noise floor."""

    def __init__(self, sr, frame_ms=20, min_db=-50.0, margin_db=12.0, start_ms=60, hang_ms=600,
                 preroll_ms=300, max_s=6.0, min_s=0.25):
        self.sr = sr
        self.frame = int(sr * frame_ms / 1000)
        self.min_db, self.margin_db = min_db, margin_db
        self.start_frames = max(1, start_ms // frame_ms)
        self.hang_frames = hang_ms // frame_ms
        self.max_frames = int(max_s * 1000 / frame_ms)
        self.min_samples = int(min_s * sr)
        self.pre = deque(maxlen=max(1, preroll_ms // frame_ms))
        self.buf = np.zeros(0, dtype=np.float32)
        self.floor_db = None
        self.active, self.cur, self.loud, self.quiet = False, [], 0, 0
        self.samples_seen = 0           # stream position, for logs
        self.start_sample = 0

    def threshold_db(self):
        return max(self.min_db, (self.floor_db if self.floor_db is not None else -90.0) + self.margin_db)

    def feed(self, block):
        """Append audio; returns the list of (start_seconds, utterance) completed in it."""
        self.buf = np.concatenate([self.buf, np.asarray(block, dtype=np.float32).reshape(-1)])
        out = []
        while len(self.buf) >= self.frame:
            f, self.buf = self.buf[:self.frame], self.buf[self.frame:]
            done = self._frame(f)
            self.samples_seen += self.frame
            if done is not None:
                out.append(done)
        return out

    def _frame(self, f):
        db = 10 * np.log10(float(np.mean(f.astype(np.float64) ** 2)) + 1e-12)
        loud = db > self.threshold_db()
        if not self.active:
            if self.floor_db is None or db < self.floor_db:
                self.floor_db = db                                   # follows quiet moments at once
            else:
                self.floor_db += (db - self.floor_db) * 0.002        # and loud ones slowly (~10 s)
            self.pre.append(f)
            self.loud = self.loud + 1 if loud else 0
            if self.loud >= self.start_frames:
                self.active, self.cur, self.quiet = True, list(self.pre), 0
                self.start_sample = self.samples_seen - (len(self.cur) - 1) * self.frame
            return None
        self.cur.append(f)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet >= self.hang_frames or len(self.cur) >= self.max_frames:
            audio = np.concatenate(self.cur)
            self.active, self.cur, self.loud = False, [], 0
            self.pre.clear()
            if len(audio) >= self.min_samples:
                return self.start_sample / self.sr, audio
        return None


class Transcriber(object):
    def __init__(self, model="small", model_dir=None, language="es"):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model, device="cpu", compute_type="int8", download_root=model_dir)
        self.language = language

    def __call__(self, audio_16k, prompt):
        with np.errstate(all="ignore"):     # numpy 2 + Apple Accelerate: spurious matmul warnings
            segments, _ = self.model.transcribe(audio_16k, language=self.language, beam_size=5,
                                                initial_prompt=prompt, condition_on_previous_text=False,
                                                without_timestamps=True, vad_filter=False)
            kept = [s.text for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
        return " ".join(kept).strip()


class Context(object):
    """What can be said right now: sections of the current song, tracks, songs."""

    def __init__(self, sections=(), tracks=(), songs=(), current=None, live=False, song_number=None):
        self.sections, self.tracks, self.songs, self.current = list(sections), list(tracks), list(songs), current
        self.song_number = song_number
        self.live = live

    @classmethod
    def from_link(cls, send=link_client.send):
        r = send({"cmd": "setlist"})
        if not r.get("ok"):
            return cls()
        st = r.get("state") or {}
        setlist = r.get("setlist") or []
        song = next((s for s in setlist if s["number"] == st.get("song")), setlist[0] if setlist else None)
        tracks = [t for t in r.get("tracks", []) if t not in GROUPS]
        return cls(song["sections"] if song else [], tracks, [(s["number"], s["title"]) for s in setlist],
                   st.get("section"), live=True, song_number=st.get("song"))

    @classmethod
    def from_song(cls, song_dir):
        song = json.loads((Path(song_dir) / "cancion.json").read_text())
        return cls([s["name"] for s in song["sections"][1:]], ["Click", "Guía", "Batería", "Bajo", "Guitarra eléctrica"])

    def prompt(self):
        return None


def listen(blocks, sr, transcribe, context, wake_words=WAKE_WORDS, dry_run=False,
           send=link_client.send, out=print):
    """Main loop. `blocks` yields mono float arrays at `sr`; `context` returns a Context."""
    seg = Segmenter(sr)
    up, down = SR // gcd(SR, sr), sr // gcd(SR, sr)
    armed_until = None
    for block in blocks:
        for start, utt in seg.feed(block):
            end = start + len(utt) / sr
            if sr != SR:
                from scipy.signal import resample_poly
                utt = resample_poly(utt, up, down).astype(np.float32)
            ctx = context()
            t0 = time.monotonic()
            text = transcribe(utt, ctx.prompt())
            ms = (time.monotonic() - t0) * 1000
            if not text:
                continue
            where = "%7.1f s" % start
            if wake_words and is_wake_only(text, wake_words):
                armed_until = end + ARMED_SECONDS
                out("%s  «%s»  … te escucho" % (where, text))
                continue
            armed = armed_until is not None and start <= armed_until
            armed_until = None
            result = parse(text, ctx.sections, ctx.tracks, ctx.songs, ctx.current,
                           () if armed else wake_words, song_number=ctx.song_number)
            if result is None:
                out("%s  «%s»  (%d ms)" % (where, text, ms))
                continue
            label, commands = result
            if not commands:
                out("%s  «%s»  → ✗ %s" % (where, text, label))
                if not dry_run:
                    send({"cmd": "message", "text": "Voz: " + label})
                continue
            if dry_run:
                out("%s  «%s»  → %s  (%d ms, sin enviar)" % (where, text, label, ms))
                continue
            errors = []
            for cmd in commands:
                r = send(cmd)
                if not r.get("ok"):
                    errors.append(r.get("error", "?"))
            if errors:
                out("%s  «%s»  → %s ✗ %s" % (where, text, label, "; ".join(errors)))
                send({"cmd": "message", "text": "Voz: %s — %s" % (label, errors[0])})
            else:
                out("%s  «%s»  → %s ✓  (%d ms)" % (where, text, label, ms))
                send({"cmd": "message", "text": "Voz: " + label})


def file_blocks(path, block_s=0.05):
    from .audio_io import decode
    audio = decode(path, SR, mono=True)[:, 0].astype(np.float32)
    n = int(SR * block_s)
    for i in range(0, len(audio), n):
        yield audio[i:i + n]
    yield np.zeros(SR, dtype=np.float32)           # close a last utterance


def mic_blocks(device, channel, sr):
    import sounddevice as sd
    q = queue.Queue()

    def callback(indata, frames, t, status):
        q.put(indata[:, channel - 1].copy())

    extra = None
    if sys.platform == "darwin":
        # never touch the interface's settings: Ableton is using it for the show
        extra = sd.CoreAudioSettings(change_device_parameters=False)
    with sd.InputStream(device=device, channels=channel, samplerate=sr, dtype="float32",
                        blocksize=int(sr * 0.05), callback=callback, extra_settings=extra):
        while True:
            yield q.get()


def list_devices():
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print("%3d  %-40s %2d entradas  %d Hz" % (i, d["name"], d["max_input_channels"], d["default_samplerate"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--devices", action="store_true", help="Lista las entradas de audio")
    ap.add_argument("--device", help="Interfaz (número o parte del nombre)")
    ap.add_argument("--channel", type=int, default=1, help="Entrada del micrófono (1, 2, …)")
    ap.add_argument("--file", help="Probar con una grabación en lugar del micrófono")
    ap.add_argument("--song", help="Con --file: carpeta de la canción, para conocer sus secciones")
    ap.add_argument("--model", default="small")
    ap.add_argument("--model-dir")
    ap.add_argument("--language", default="es")
    ap.add_argument("--wake", default=WAKE_WORDS[0], help="Palabra de activación (por defecto: secuencia)")
    ap.add_argument("--no-wake", action="store_true", help="Sin palabra de activación (solo para pruebas)")
    ap.add_argument("--dry-run", action="store_true", help="Escuchar y mostrar, sin enviar nada a Ableton")
    args = ap.parse_args(argv)

    if args.devices:
        list_devices()
        return 0
    wake = () if args.no_wake else (args.wake.lower(),)
    print("Cargando el modelo de voz…", flush=True)
    transcribe = Transcriber(args.model, args.model_dir, args.language)
    if args.file:
        fixed = Context.from_song(args.song) if args.song else Context()
        blocks, sr = file_blocks(args.file), SR
        context = (lambda: fixed) if args.dry_run or args.song else Context.from_link
    else:
        import sounddevice as sd
        device = int(args.device) if args.device and args.device.isdigit() else args.device
        sr = int(sd.query_devices(device, "input")["default_samplerate"])
        blocks = mic_blocks(device, args.channel, sr)
        context = Context.from_link
        if not args.dry_run and not Context.from_link().live:
            print(link_client.NOT_RUNNING)
        print("Escuchando (entrada %d, %d Hz). Di «%s, …». Ctrl+C para salir." % (
            args.channel, sr, wake[0].capitalize() if wake else "…"), flush=True)
    try:
        listen(blocks, sr, transcribe, context, wake, args.dry_run)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
