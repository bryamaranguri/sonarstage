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
import warnings
import queue
import sys
import time
from collections import deque
from math import gcd
from pathlib import Path

import numpy as np

from . import link_client
from .voice_commands import WAKE_WORDS, parse, wake_rest

SR = 16000
warnings.filterwarnings("ignore", message=".*OpenSSL.*")      # urllib3 on macOS's Python 3.9, harmless
ARMED_SECONDS = 4.0      # after a lone "Secuencia", the next phrase within this time is the order
GROUPS = {"EN VIVO", "SECUENCIA", "CUES", "CONTROL"}
# Whisper's prompt is only the wake word. A prompt with the whole vocabulary made it "hear"
# section names and "Siguiente" over music with no speech; "Secuencia." alone raised the
# recorded orders understood from 77 % to 85 % with no false alarms (docs/hallazgos).
PROMPT = "Secuencia."


class Segmenter(object):
    """Cuts a stream into utterances by level, against an adaptive noise floor."""

    def __init__(self, sr, frame_ms=20, min_db=-50.0, margin_db=12.0, start_ms=60, hang_ms=400,
                 preroll_ms=300, max_s=6.0, min_s=0.25, stream=None):
        self.sr = sr
        self.frame_ms = frame_ms
        self.stream = stream            # recognizes while you talk and may end the phrase sooner
        self.end_quiet_ms = hang_ms     # silence waited before the last phrase was closed
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
                if self.stream is not None:
                    self.stream.start(self.cur)
            return None
        self.cur.append(f)
        self.quiet = 0 if loud else self.quiet + 1
        early = False
        if self.stream is not None:
            self.stream.frame(f)
            early = self.quiet > 0 and self.stream.done(self.quiet * self.frame_ms)
        if early or self.quiet >= self.hang_frames or len(self.cur) >= self.max_frames:
            self.end_quiet_ms = self.quiet * self.frame_ms
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


class MLXTranscriber(object):
    """Whisper on the Mac's GPU (Apple Silicon): pip install mlx-whisper."""

    def __init__(self, repo="mlx-community/whisper-large-v3-turbo", language="es"):
        import mlx_whisper
        self.mlx_whisper, self.repo, self.language = mlx_whisper, repo, language

    def __call__(self, audio_16k, prompt):
        with np.errstate(all="ignore"):
            r = self.mlx_whisper.transcribe(audio_16k, path_or_hf_repo=self.repo, language=self.language,
                                            temperature=0.0, initial_prompt=prompt,
                                            condition_on_previous_text=False, verbose=None)
        return " ".join(s["text"] for s in r.get("segments", [])
                        if s.get("no_speech_prob", 0) < 0.6 and s.get("avg_logprob", 0) > -1.0).strip()


class VoskTranscriber(object):
    """Closed vocabulary: Vosk can only hear the words of the orders (pip install vosk and
    the small Spanish model, vosk-model-small-es-0.42, in the models folder)."""

    def __init__(self, model_dir):
        import json as _json
        from vosk import KaldiRecognizer, Model, SetLogLevel
        from .voice_commands import order_words
        SetLogLevel(-2)                 # also quiet "word missing in vocabulary" (they are skipped)
        path = next(Path(model_dir).glob("vosk-model*es*"))
        self.json = _json
        self.model = Model(str(path))
        self.grammar = _json.dumps(order_words() + ["[unk]"], ensure_ascii=False)
        self.rec = KaldiRecognizer(self.model, SR, self.grammar)

    def __call__(self, audio_16k, prompt=None):
        self.rec.Reset()
        self.rec.AcceptWaveform(_pcm16(audio_16k))
        return _clean(self.json.loads(self.rec.FinalResult()).get("text", ""))

    def grammar_for(self, sections=()):
        from .voice_commands import order_words
        return self.json.dumps(order_words(sections) + ["[unk]"], ensure_ascii=False)

    def stream(self, sr, on_start, settle, sections=None):
        """Recognize while the phrase is spoken. `settle(text)` says how much silence (ms)
        closes it, or None to wait the full time. `sections()`: names of the song playing,
        added to the vocabulary when the song changes."""
        from vosk import KaldiRecognizer
        return VoskStream(KaldiRecognizer(self.model, sr, self.grammar), self.json, on_start, settle,
                          sections, self.grammar_for)


def _pcm16(x):
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


def _clean(text):
    return " ".join(w for w in text.split() if w != "[unk]")


class VoskStream(object):
    def __init__(self, rec, json_module, on_start, settle, sections=None, grammar_for=None):
        self.rec, self.json, self.on_start, self.settle = rec, json_module, on_start, settle
        self.sections, self.grammar_for = sections, grammar_for
        self.said, self.known = [], None

    def start(self, frames):
        self.on_start()
        names = tuple(self.sections()) if self.sections else ()
        if names != self.known and self.grammar_for is not None:
            self.known = names
            try:
                self.rec.SetGrammar(self.grammar_for(names))
            except Exception:
                pass                                   # older vosk: the fixed vocabulary stays
        self.rec.Reset()
        self.said = []
        for f in frames:
            self.frame(f)

    def frame(self, f):
        if self.rec.AcceptWaveform(_pcm16(f)):          # Vosk closed a piece on its own
            self.said.append(_clean(self.json.loads(self.rec.Result()).get("text", "")))

    def text_so_far(self):
        return " ".join(self.said + [_clean(self.json.loads(self.rec.PartialResult()).get("partial", ""))]).strip()

    def done(self, quiet_ms):
        need = self.settle(self.text_so_far())
        return need is not None and quiet_ms >= need

    def final(self):
        return " ".join(self.said + [_clean(self.json.loads(self.rec.FinalResult()).get("text", ""))]).strip()


class Confirmer(object):
    """Spoken confirmations (voice_prompts.py), loaded at the interface's rate and handed to
    `play` (the one stream that is already open: opening an output per phrase next to the
    mic stopped the mic on a real Mac)."""

    def __init__(self, folder, sr, play, gain_db=0.0):
        import soundfile as sf
        from scipy.signal import resample_poly
        self.sr, self.play = sr, play
        self.clips = {}
        g = 10 ** (gain_db / 20)
        for f in Path(folder).glob("*.wav"):
            x, file_sr = sf.read(str(f), dtype="float32")
            if file_sr != sr:
                x = resample_poly(x, sr // gcd(sr, file_sr), file_sr // gcd(sr, file_sr))
            self.clips[f.stem] = (x * g).astype(np.float32)
        if not self.clips:
            raise ValueError("no hay frases en %s" % folder)

    def __call__(self, key):
        x = self.clips.get(key)
        if x is None:
            return False
        try:
            self.play(x)
            return True
        except Exception as e:                       # a confirmation must never stop the listener
            print("  (no pude reproducir la confirmación: %s)" % e)
            return False


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
        return PROMPT


def _unfinished(rest):
    """Only "Secuencia…" or "Secuencia, vamos…" wait for the rest; a whole sentence that is
    not an order ("Banda, en el coro bajamos") is dropped, not carried into the next one."""
    from .voice_commands import FILLER, MOVE
    return all(w in FILLER or w in MOVE for w in rest.split())


class Interpreter(object):
    """Text of each phrase -> what to do, with the wake word memory between phrases.

    A phrase that opens with the wake word but is not a whole order yet ("Secuencia…",
    "Secuencia, vamos…") waits ARMED_SECONDS for the rest. Shared by the live loop and by
    voice_bench, so what is measured is exactly what runs on stage.
    """

    def __init__(self, wake_words=WAKE_WORDS):
        self.wake_words = wake_words
        self.armed_until, self.prefix = None, ""

    def peek(self, text, start, ctx):
        """What `text` would do now, without remembering anything (for streaming engines)."""
        saved = self.armed_until, self.prefix
        try:
            return self.hear(text, start, start, ctx)
        finally:
            self.armed_until, self.prefix = saved

    def hear(self, text, start, end, ctx):
        """(kind, label, commands): kind is 'ignored', 'armed', 'refused' or 'command'."""
        if not text:
            return "ignored", "", []
        own = None if not self.wake_words else wake_rest(text, self.wake_words)
        # a phrase with its own wake word starts over: what was waiting is dropped
        armed = own is None and self.armed_until is not None and start <= self.armed_until
        said = (self.prefix + " " + text).strip() if armed else text
        rest = None if armed else own
        result = parse(said, ctx.sections, ctx.tracks, ctx.songs, ctx.current,
                       () if armed else self.wake_words, song_number=ctx.song_number)
        self.armed_until, self.prefix = None, ""
        if result is None and rest is not None and _unfinished(rest):
            self.armed_until, self.prefix = end + ARMED_SECONDS, rest
            return "armed", "…", []
        if result is None:
            return "ignored", "", []
        label, commands = result
        return ("command" if commands else "refused"), label, commands


# Silence that closes a phrase. Measured on Bryam's recordings: inside an order words are
# at most ~0.1 s apart (90 %), 0.24 s at worst ("vamos… verso").
SETTLE_DONE_MS = 200       # the phrase is already a whole order that cannot go on
SETTLE_NUMBER_MS = 300     # it ends in a section that has numbers here ("coro" → "coro dos"?)
WAIT_FOR_MORE = {"siguiente", "proxima", "proximo", "next", "otra", "una", "vez", "al", "a", "la", "el",
                 "de", "del", "vamos", "ir", "secuencia"}


def settle_ms(kind, text, ctx):
    """How much silence closes the phrase `text` (None: the full wait, it is not an order yet)."""
    if kind != "command":
        return None
    from .voice_commands import normalize
    words = normalize(text)
    last = words[-1] if words else ""
    if last in WAIT_FOR_MORE:
        return None
    numbered = set()
    for name in ctx.sections:
        w = normalize(name)
        if len(w) > 1 and w[-1].isdigit():
            numbered.update(w[:-1])
    return SETTLE_NUMBER_MS if last in numbered else SETTLE_DONE_MS


def listen(blocks, sr, transcribe, context, wake_words=WAKE_WORDS, dry_run=False,
           send=link_client.send, out=print, record=None, confirm=None):
    """Main loop. `blocks` yields mono float arrays at `sr`; `context` returns a Context.
    `record` (a folder) keeps every phrase as a WAV plus a line in registro.tsv."""
    up, down = SR // gcd(SR, sr), sr // gcd(SR, sr)
    interpreter = Interpreter(wake_words)
    holder = {"ctx": None, "start": 0.0}
    stream = None
    if hasattr(transcribe, "stream"):
        def on_start():
            holder["ctx"] = context()

        def settle(text):
            ctx = holder["ctx"] or Context()
            kind, _, _ = interpreter.peek(text, seg.start_sample / sr, ctx)
            return settle_ms(kind, text, ctx)
        stream = transcribe.stream(sr, on_start, settle,
                                   sections=lambda: (holder["ctx"] or Context()).sections)
    seg = Segmenter(sr, stream=stream)
    n, log = 0, None
    if record:
        Path(record).mkdir(parents=True, exist_ok=True)
        log = open(Path(record) / "registro.tsv", "a", encoding="utf-8")
    for block in blocks:
        for start, utt in seg.feed(block):
            end = start + len(utt) / sr
            t0 = time.monotonic()
            if stream is not None:
                ctx = holder["ctx"] or context()
                text = stream.final()
            if sr != SR:
                from scipy.signal import resample_poly
                utt = resample_poly(utt, up, down).astype(np.float32)
            if stream is None:
                ctx = context()
                text = transcribe(utt, ctx.prompt())
            ms = (time.monotonic() - t0) * 1000 + seg.end_quiet_ms          # after you stop talking
            kind, label, commands = interpreter.hear(text, start, end, ctx)
            where = "%7.1f s" % start
            errors, reply_state = [], None
            if kind == "armed":
                out("%s  «%s»  … te escucho" % (where, text))
            elif kind == "ignored":
                if text:
                    out("%s  «%s»  (%d ms)" % (where, text, ms))
            elif kind == "refused":
                out("%s  «%s»  → ✗ %s" % (where, text, label))
                if not dry_run:
                    send({"cmd": "message", "text": "Voz: " + label})
            elif dry_run:
                out("%s  «%s»  → %s  (%d ms, sin enviar)" % (where, text, label, ms))
            else:
                for cmd in commands:
                    r = send(cmd)
                    reply_state = r.get("state")
                    if not r.get("ok"):
                        errors.append(r.get("error", "?"))
                    elif cmd["cmd"] == "next_song" and (r.get("state") or {}).get("song"):
                        commands = [{"cmd": "song", "number": r["state"]["song"]}]   # say which one
                if errors:
                    out("%s  «%s»  → %s ✗ %s" % (where, text, label, "; ".join(errors)))
                    send({"cmd": "message", "text": "Voz: %s — %s" % (label, errors[0])})
                else:
                    out("%s  «%s»  → %s ✓  (%d ms)" % (where, text, label, ms))
                    send({"cmd": "message", "text": "Voz: " + label})
            if confirm is not None:
                from .voice_prompts import key_for
                key = key_for(kind, commands, errors, reply_state)
                if key:
                    confirm(key)
            if log is not None:
                n += 1
                name = "%s-%03d.wav" % (time.strftime("%Y%m%d-%H%M%S"), n)
                import soundfile as sf
                sf.write(str(Path(record) / name), utt, SR, subtype="PCM_16")
                log.write("%s\t%.2f\t%s\t%s\t%d\n" % (name, start, text, label, ms))
                log.flush()


def file_blocks(path, block_s=0.05):
    from .audio_io import decode
    audio = decode(path, SR, mono=True)[:, 0].astype(np.float32)
    n = int(SR * block_s)
    for i in range(0, len(audio), n):
        yield audio[i:i + n]
    yield np.zeros(SR, dtype=np.float32)           # close a last utterance


class AudioIO(object):
    """One stream on the interface for the whole show: the mic comes in on `in_channel`
    and, if `out_channel` is given, the confirmations go out on it (silence otherwise).
    Never touches the interface's settings: Ableton is using it. If the mic stops arriving
    (2 s without audio), the stream is reopened."""

    STALL_S = 2.0

    def __init__(self, device, in_channel, out_channel=None, out=print):
        import sounddevice as sd
        import threading
        self.sd, self.device, self.in_channel, self.out_channel, self.out = sd, device, in_channel, out_channel, out
        self.sr = int(sd.query_devices(device, "input")["default_samplerate"])
        self.extra = sd.CoreAudioSettings(change_device_parameters=False) if sys.platform == "darwin" else None
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.playing, self.pos = None, 0
        self.stream = None

    def _in(self, indata, frames, t, status):
        self.q.put(indata[:, self.in_channel - 1].copy())

    def _duplex(self, indata, outdata, frames, t, status):
        self.q.put(indata[:, self.in_channel - 1].copy())
        outdata.fill(0)
        with self.lock:
            if self.playing is not None:
                n = min(frames, len(self.playing) - self.pos)
                outdata[:n, self.out_channel - 1] = self.playing[self.pos:self.pos + n]
                self.pos += n
                if self.pos >= len(self.playing):
                    self.playing = None

    def open(self):
        block = int(self.sr * 0.02)
        if self.out_channel:
            try:
                self.stream = self.sd.Stream(device=(self.device, self.device),
                                             channels=(self.in_channel, self.out_channel),
                                             samplerate=self.sr, dtype="float32", blocksize=block,
                                             callback=self._duplex, extra_settings=(self.extra, self.extra))
                self.stream.start()
                return True
            except Exception as e:
                self.out("Sin confirmación hablada: no pude abrir la salida %d (%s)" % (self.out_channel, e))
                self.out_channel = None
        self.stream = self.sd.InputStream(device=self.device, channels=self.in_channel, samplerate=self.sr,
                                          dtype="float32", blocksize=block, callback=self._in,
                                          extra_settings=self.extra)
        self.stream.start()
        return False

    def close(self):
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def play(self, samples):
        if not self.out_channel:
            raise RuntimeError("sin salida")
        with self.lock:
            self.playing, self.pos = samples, 0

    def blocks(self):
        while True:
            try:
                yield self.q.get(timeout=self.STALL_S)
            except queue.Empty:
                self.out("⚠ El micrófono dejó de llegar: reconectando la entrada…")
                self.close()
                time.sleep(0.5)
                try:
                    self.open()
                    self.out("  reconectado.")
                except Exception as e:
                    self.out("  no se pudo (%s); vuelvo a intentar." % e)


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
    ap.add_argument("--engine", choices=["whisper", "mlx", "vosk"],
                    help="vosk (vocabulario cerrado; por defecto si su modelo está en --model-dir), "
                         "mlx (Whisper turbo en la gráfica de la Mac) o whisper (procesador)")
    ap.add_argument("--model", default="small")
    ap.add_argument("--model-dir")
    ap.add_argument("--language", default="es")
    ap.add_argument("--wake", nargs="+", default=list(WAKE_WORDS),
                    help="Palabras de activación (por defecto: secuencia banda)")
    ap.add_argument("--no-wake", action="store_true", help="Sin palabra de activación (solo para pruebas)")
    ap.add_argument("--dry-run", action="store_true", help="Escuchar y mostrar, sin enviar nada a Ableton")
    ap.add_argument("--record", help="Carpeta donde guardar cada frase (WAV + registro.tsv) para pruebas")
    ap.add_argument("--voices", help="Carpeta de frases de confirmación (por defecto: voces junto a --model-dir)")
    ap.add_argument("--confirm-channel", type=int, default=2, help="Salida de la interfaz para la confirmación (la del click)")
    ap.add_argument("--confirm-gain", type=float, default=0.0, help="Volumen de la confirmación en dB")
    ap.add_argument("--no-confirm", action="store_true", help="Sin confirmación hablada")
    args = ap.parse_args(argv)

    if args.devices:
        list_devices()
        return 0
    wake = () if args.no_wake else tuple(w.lower() for w in args.wake)
    print("Cargando el modelo de voz…", flush=True)
    if args.engine is None:
        has_vosk = args.model_dir and any(Path(args.model_dir).glob("vosk-model*es*"))
        args.engine = "vosk" if has_vosk else "whisper"
    print("Motor: %s" % args.engine, flush=True)
    if args.engine == "vosk":
        transcribe = VoskTranscriber(args.model_dir)
    elif args.engine == "mlx":
        transcribe = MLXTranscriber(language=args.language)
    else:
        transcribe = Transcriber(args.model, args.model_dir, args.language)
    if args.file:
        fixed = Context.from_song(args.song) if args.song else Context()
        blocks, sr = file_blocks(args.file), SR
        context = (lambda: fixed) if args.dry_run or args.song else Context.from_link
    confirm = None
    if not args.file:
        device = int(args.device) if args.device and args.device.isdigit() else args.device
        voices = Path(args.voices) if args.voices else (Path(args.model_dir).parent / "voces" if args.model_dir else None)
        want_confirm = not args.no_confirm and voices is not None and voices.is_dir()
        audio = AudioIO(device, args.channel, args.confirm_channel if want_confirm else None)
        if audio.open():
            try:
                confirm = Confirmer(voices, audio.sr, audio.play, args.confirm_gain)
                print("Confirmación hablada por la salida %d." % args.confirm_channel)
            except Exception as e:
                print("Sin confirmación hablada: %s" % e)
        elif not args.no_confirm and not want_confirm:
            print("Sin confirmación hablada: no hay frases (python -m sonarstage_import.voice_prompts %s)."
                  % (voices or "<carpeta>"))
        blocks, sr = audio.blocks(), audio.sr
        context = Context.from_link
        if not args.dry_run and not Context.from_link().live:
            print(link_client.NOT_RUNNING)
        print("Escuchando (entrada %d, %d Hz). Di «%s, …». Ctrl+C para salir." % (
            args.channel, sr, "» o «".join(w.capitalize() for w in wake) if wake else "…"), flush=True)
    try:
        listen(blocks, sr, transcribe, context, wake, args.dry_run, record=args.record, confirm=confirm)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
