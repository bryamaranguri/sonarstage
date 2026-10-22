"""Name the sections from what the guide says ("Chorus", "Verso 2", "Puente"…).

    python -m sonarstage_import.label <song> [--model small] [--model-dir DIR] [--apply]

Transcribes the guide offline with Whisper (faster-whisper) with word timestamps, takes
the words spoken in each announcement (the bars just before a section starts, see
library.sections_from_cues) and maps them to a name in Spanish and a kind. Counting
("one, two, three, four") is ignored. Without --apply it only shows the proposal.

The model downloads once (first run, needs internet) into --model-dir; after that it
works offline.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

from .audio_io import decode

SR = 16000
PROMPT = ("Intro. Verse 1. Verse 2. Pre-Chorus. Chorus. Bridge. Instrumental. Interlude. Tag. "
          "Outro. Ending. Breakdown. Vamp. Intro. Verso 1. Pre coro. Coro. Puente. Interludio. Final.")

# order matters: pre-chorus before chorus
KINDS = [
    ("prechorus", "Pre coro", r"\bpre\s*-?\s*(chorus|coro)\b|\bprecoro\b|\bprechorus\b"),
    ("intro", "Intro", r"\bintro(duccion)?\b"),
    ("chorus", "Coro", r"\bchorus\b|\bcoro\b|\bestribillo\b|\brefrain\b"),
    ("verse", "Verso", r"\bverse\b|\bverso\b|\bestrofa\b"),
    ("bridge", "Puente", r"\bbridge\b|\bpuente\b"),
    ("interlude", "Interludio", r"\binterlude\b|\binterludio\b|\bturn\s*around\b|\bturnaround\b"),
    ("interlude", "Instrumental", r"\binstrumental\b"),
    ("tag", "Tag", r"\btag\b"),
    ("outro", "Final", r"\boutro\b|\bending\b|\bfinal\b|\bfin\b"),
    ("other", "Break", r"\bbreak\s*down\b|\bbreakdown\b|\bbreak\b"),
    ("other", "Vamp", r"\bvamp\b"),
    ("other", "Build", r"\bbuild\b|\bbuilding\b"),
    ("other", "Exhortación", r"\bexhortation\b|\bexhortacion\b"),
    ("other", "A cappella", r"\ba\s*cappella\b|\bacapella\b"),
]
NUMBERS = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "one": 1, "two": 2, "to": 2, "too": 2, "three": 3,
           "four": 4, "for": 4, "five": 5, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "i": 1, "ii": 2, "iii": 3}


def normalise(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9\s-]", " ", t)


def name_from_words(text):
    """('Verso 2', 'verse') from 'Verse two', or None if no section word is heard."""
    t = normalise(text)
    for kind, display, pattern in KINDS:
        m = re.search(pattern, t)
        if m:
            after = t[m.end():].split()
            counting = len(after) > 1 and after[1] in NUMBERS          # "Chorus, two, three, four"
            if after and after[0] in NUMBERS and not counting and kind in ("verse", "chorus", "prechorus", "bridge", "interlude"):
                return "%s %d" % (display, NUMBERS[after[0]]), kind
            return display, kind
    return None


def transcribe(audio_16k, model="small", model_dir=None, language=None):
    """[(start_s, end_s, word)] for the whole guide."""
    from faster_whisper import WhisperModel           # optional dependency
    m = WhisperModel(model, device="cpu", compute_type="int8", download_root=model_dir)
    segments, info = m.transcribe(audio_16k, language=language, word_timestamps=True, vad_filter=True,
                                  initial_prompt=PROMPT, condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append((float(w.start), float(w.end), w.word.strip()))
    return words, info.language


def bar_time(song, bar):
    t = song["tempo"]
    bpb = int(t["timeSignature"].split("/")[0])
    return t.get("firstDownbeatSec", 0.0) + (bar - 1) * bpb * 60.0 / t["bpm"]


def propose(song, words, window_bars=2):
    """For each section: the words heard in the bars before it and the proposed name."""
    out = []
    for i, sec in enumerate(song["sections"]):
        if i == 0:
            out.append({"index": 1, "startBar": sec["startBar"], "old": sec["name"], "heard": "",
                        "name": sec["name"], "kind": sec.get("kind", "other")})
            continue
        end = bar_time(song, sec["startBar"])
        start = bar_time(song, max(1, sec["startBar"] - window_bars)) - 0.25
        heard = " ".join(w for a, b, w in words if start <= a < end)
        found = name_from_words(heard)
        out.append({"index": i + 1, "startBar": sec["startBar"], "old": sec["name"], "heard": heard,
                    "name": found[0] if found else sec["name"], "kind": found[1] if found else sec.get("kind", "other"),
                    "matched": bool(found)})
    return out


def apply(song_path, song, proposal):
    for sec, p in zip(song["sections"], proposal):
        if p.get("matched"):
            sec["name"], sec["kind"], sec["guide"] = p["name"], p["kind"], p["heard"]
    song_path.write_text(json.dumps(song, indent=1, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("--model", default="small")
    ap.add_argument("--model-dir")
    ap.add_argument("--language", help="es o en (por defecto se detecta)")
    ap.add_argument("--apply", action="store_true", help="Guardar los nombres en cancion.json")
    args = ap.parse_args(argv)
    song_dir = Path(args.song)
    song_path = song_dir / "cancion.json"
    song = json.loads(song_path.read_text())
    guide = next((s for s in song["stems"] if s["role"] == "guide"), None)
    if guide is None:
        print("La canción no tiene guía.", file=sys.stderr)
        return 1
    audio = decode(song_dir / "originales" / guide["file"], SR, mono=True)[:, 0].astype(np.float32)
    words, lang = transcribe(audio, args.model, args.model_dir, args.language)
    proposal = propose(song, words)
    print(f"{song['title']} — guía en «{lang}», {len(words)} palabras")
    print(f"{'#':>3} {'compás':>6}  {'antes':12} {'nuevo':14} escuchado")
    for p in proposal:
        mark = "" if p.get("matched", True) else "  (sin cambio)"
        print(f"{p['index']:>3} {p['startBar']:>6}  {p['old'][:12]:12} {p['name'][:14]:14} {p['heard'][:60]}{mark}")
    if args.apply:
        apply(song_path, song, proposal)
        print("Nombres guardados en cancion.json.")
    else:
        print("Vista previa. Agrega --apply para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
