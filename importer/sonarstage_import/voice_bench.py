"""Compare speech engines on recorded phrases (voice.py --record), with the same wake word
and phrase logic that runs on stage.

    python -m sonarstage_import.voice_bench <carpeta voz> --model-dir <modelos> --engines whisper vosk mlx-small mlx-turbo

The folder needs registro.tsv (written while recording) and esperado.tsv: per file the
order meant ("repeat", "goto:Coro", "mute:Batería", …), "wake" for a lone "Secuencia" or
"none" for talk that is not an order. Writes resultados-<engine>.tsv next to them.

Engines:
  whisper         faster-whisper small on the CPU (what voice.py uses today)
  whisper-prompt  the same, told that "Secuencia" is coming
  mlx-small       Whisper small on the Mac's GPU (pip install mlx-whisper; Apple Silicon only)
  mlx-turbo       Whisper large-v3-turbo on the GPU
  vosk            closed vocabulary: can only hear the order words (pip install vosk + model)
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from .voice import ARMED_SECONDS, Context, Interpreter, Transcriber  # noqa: F401
from .voice_commands import (AFTER, CANCEL, HOLD, LAST, MUTE, NEXT, PLAY, PREVIOUS, RELEASE, REPEAT, SKIP,
                             SONG, STOP, UNMUTE, WAKE_WORDS)

# what the band was playing while recording (Prueba 3): song 2 of 2, in a chorus
SECTIONS = ["Intro", "Verso 1", "Pre coro", "Coro 1", "Verso 2", "Build", "Coro 2", "Tag", "Final"]
TRACKS = ["Click", "Guía", "Batería", "Bajo", "Guitarra eléctrica", "Secuencia"]
SONGS = [(1, "Holy Forever"), (2, "Alegras mis días")]


def context():
    return Context(SECTIONS, TRACKS, SONGS, current="Coro 1", song_number=2)


def key_of(kind, commands):
    if kind == "armed":
        return "wake"
    if kind != "command":
        return "-"
    c = commands[0]
    if c["cmd"] == "goto":
        return "goto:" + c["section"]
    if c["cmd"] == "song":
        return "song:%d" % c["number"]
    if c["cmd"] == "mute":
        return ("mute:" if c["on"] else "unmute:") + c["track"]
    return c["cmd"]


def judge(expected, got):
    if expected == "none":
        return "falsa alarma" if got not in ("-", "wake") else "ok"
    if expected == "wake":
        return "ok" if got in ("-", "wake") else "error"
    if got == expected or (expected.endswith("*") and got.startswith(expected[:-1])):
        return "ok"
    return "no entendió" if got in ("-", "wake") else "error"


# --- engines ------------------------------------------------------------------------------

def whisper_cpu(args, prompt=None):
    t = Transcriber("small", args.model_dir, "es")
    return lambda audio: t(audio, prompt)


def mlx(repo):
    def make(args):
        import mlx_whisper

        def run(audio):
            with np.errstate(all="ignore"):
                r = mlx_whisper.transcribe(audio, path_or_hf_repo=repo, language="es", temperature=0.0,
                                           condition_on_previous_text=False, verbose=None)
            return " ".join(s["text"] for s in r.get("segments", [])
                            if s.get("no_speech_prob", 0) < 0.6 and s.get("avg_logprob", 0) > -1.0).strip()
        return run
    return make


VOSK_WORDS = sorted(set(WAKE_WORDS) | CANCEL | STOP | NEXT | PREVIOUS | LAST | SONG | MUTE | UNMUTE | HOLD |
                    REPEAT | RELEASE | PLAY | AFTER | SKIP | {"después", "va", "es",
                        "canción", "batería", "guitarra", "bajo", "teclado", "guía", "clic", "metrónomo",
                        "intro", "verso", "pre", "coro", "puente", "final", "instrumental", "interludio", "tag",
                        "uno", "dos", "tres", "cuatro", "cinco", "primera", "segunda", "tercera", "última",
                        "próxima", "otra", "vez", "más", "de", "nuevo", "vamos", "al", "a", "la", "el", "ir",
                        "desde", "con", "en", "banda", "y"})


def vosk(args):
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    path = Path(args.vosk_model) if args.vosk_model else next(Path(args.model_dir).glob("vosk-model*es*"))
    model = Model(str(path))
    rec = KaldiRecognizer(model, 16000, json.dumps(VOSK_WORDS + ["[unk]"], ensure_ascii=False))

    def run(audio):
        rec.Reset()
        rec.AcceptWaveform((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        return json.loads(rec.FinalResult()).get("text", "").replace("[unk]", "").strip()
    return run


ENGINES = {
    "whisper": whisper_cpu,
    "whisper-prompt": lambda args: whisper_cpu(args, prompt="Secuencia."),
    "mlx-small": mlx("mlx-community/whisper-small-mlx"),
    "mlx-turbo": mlx("mlx-community/whisper-large-v3-turbo"),
    "vosk": vosk,
}


# --- run ----------------------------------------------------------------------------------

def load(folder):
    import soundfile as sf
    folder = Path(folder)
    starts = {}
    for line in (folder / "registro.tsv").read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            starts[cols[0]] = float(cols[1])
    rows = []
    for line in (folder / "esperado.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, expected = line.split("\t")[:2]
        audio, sr = sf.read(str(folder / name), dtype="float32")
        rows.append((name, expected, starts.get(name, 0.0), audio))
    return rows


def transcribe_all(rows, make_run, cache_path=None, budget=None):
    """{file: (text, ms)}. With `cache_path`, what was already transcribed is reused and each
    new phrase is appended as it is done, so a long run can be split (`budget` seconds)."""
    done = {}
    if cache_path and Path(cache_path).exists():
        for line in Path(cache_path).read_text(encoding="utf-8").splitlines():
            name, ms, text = (line.split("\t") + ["", ""])[:3]
            done[name] = (text, float(ms))
    todo = [r for r in rows if r[0] not in done]
    if todo:
        run = make_run()
        run(todo[0][3])                               # warm up (first call loads kernels)
    t_start = time.monotonic()
    cache = open(cache_path, "a", encoding="utf-8") if cache_path else None
    for name, expected, start, audio in todo:
        if budget and time.monotonic() - t_start > budget:
            break
        t0 = time.monotonic()
        text = run(audio)
        done[name] = (text, (time.monotonic() - t0) * 1000)
        if cache:
            cache.write("%s\t%.0f\t%s\n" % (name, done[name][1], text.replace("\t", " ")))
            cache.flush()
    return done


def bench(rows, texts, interpreter=None):
    interpreter = interpreter or Interpreter()
    out = []
    for name, expected, start, audio in rows:
        text, ms = texts[name]
        kind, label, commands = interpreter.hear(text, start, start + len(audio) / 16000, context())
        got = key_of(kind, commands)
        out.append((name, expected, got, judge(expected, got), ms, text))
    return out


def summary(engine, results):
    orders = [r for r in results if r[1] not in ("none", "wake")]
    talk = [r for r in results if r[1] == "none"]
    ok = sum(r[3] == "ok" for r in orders)
    wrong = sum(r[3] == "error" for r in results)
    missed = sum(r[3] == "no entendió" for r in orders)
    false = sum(r[3] == "falsa alarma" for r in talk)
    ms = sorted(r[4] for r in orders)
    p90 = ms[min(len(ms) - 1, int(0.9 * len(ms)))] if ms else 0
    return "%-15s %3d/%-3d bien (%3.0f %%)  %2d mal  %2d sin entender  %2d falsas alarmas en %d frases  " \
           "%4.0f ms (90 %%: %4.0f ms)" % (engine, ok, len(orders), 100.0 * ok / max(1, len(orders)), wrong,
                                         missed, false, len(talk), statistics.median(ms) if ms else 0, p90)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--model-dir")
    ap.add_argument("--vosk-model")
    ap.add_argument("--engines", nargs="+", default=["whisper"], choices=sorted(ENGINES))
    ap.add_argument("--budget", type=float, help="Segundos máximos por motor; se continúa en la siguiente corrida")
    args = ap.parse_args(argv)
    rows = load(args.folder)
    lines = []
    for engine in args.engines:
        print("%s…" % engine, flush=True)
        import platform
        # one cache per machine: the times only mean something on the computer that measured them
        cache = Path(args.folder) / ("textos-%s-%s-%s.tsv" % (engine, platform.system(), platform.machine()))
        try:
            texts = transcribe_all(rows, lambda: ENGINES[engine](args), cache, args.budget)
        except Exception as e:
            print("  no disponible: %s" % e)
            continue
        if len(texts) < len(rows):
            print("  %d de %d frases; vuelve a correrlo para continuar" % (len(texts), len(rows)))
            continue
        results = bench(rows, texts)
        with open(Path(args.folder) / ("resultados-%s.tsv" % engine), "w", encoding="utf-8") as f:
            f.write("archivo\tesperado\tobtenido\tresultado\tms\ttexto\n")
            for r in results:
                f.write("%s\t%s\t%s\t%s\t%.0f\t%s\n" % r)
        lines.append(summary(engine, results))
        print("  " + lines[-1], flush=True)
    print("\nTiempo = solo reconocer; en vivo se suman 400 ms esperando que termines de hablar.")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
