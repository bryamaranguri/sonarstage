"""Short spoken confirmations for the director's ear ("Coro", "Repetimos", "Canción dos").

    python -m sonarstage_import.voice_prompts <carpeta de voces>          (en la Mac: usa `say`)

Every phrase is rendered once with a Spanish voice of macOS into <folder>/<key>.wav (mono,
48 kHz, same level for all) plus voces.json. voice.py plays the one that matches what it
understood. `key_for` is pure, so which phrase goes with which order is tested.
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

NUMBER_WORDS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
                "once", "doce", "trece", "catorce", "quince"]
SECTION_NAMES = ["Cuenta", "Intro", "Verso", "Pre coro", "Coro", "Puente", "Interludio", "Instrumental",
                 "Tag", "Final", "Break", "Vamp", "Build", "Exhortación", "A cappella"]
TRACK_WORDS = {"bateria": "batería", "bajo": "bajo", "guitarra": "guitarra", "teclado": "teclado",
               "guia": "guía", "click": "click", "piano": "piano", "voz": "voz"}
FIXED = {"repeat": "Repetimos", "hold": "En bucle", "release": "Seguimos", "cancel": "Cancelado",
         "next_section": "Siguiente", "next_song": "Siguiente canción", "play": "Dale", "stop": "Paramos",
         "refused": "No entendí", "error": "No se pudo", "first_song": "Ya es la primera"}
SONGS = 12
PREFERRED_VOICES = ("es_MX", "es_419", "es_US", "es_ES")
TARGET_RMS_DB = -20.0
PEAK_DB = -1.0


def slug(text):
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def spoken(text):
    """'Verso 2' -> 'Verso dos'."""
    return re.sub(r"\d+", lambda m: NUMBER_WORDS[int(m.group())] if int(m.group()) < len(NUMBER_WORDS)
                  else m.group(), text)


def catalog():
    """{key: text} for every phrase."""
    out = dict(FIXED)
    for n in range(1, SONGS + 1):
        w = NUMBER_WORDS[n]
        out["song-%d" % n] = "Canción %s" % w
        out["next-is-%d" % n] = "Después, la %s" % w
        out["skip-%d" % n] = "Sin la %s" % w
    for name in SECTION_NAMES:
        out["section-" + slug(name)] = name
        for n in range(1, 5):
            out["section-" + slug("%s %d" % (name, n))] = spoken("%s %d" % (name, n))
    for key, word in TRACK_WORDS.items():
        out["mute-" + key] = "Sin " + word
        out["unmute-" + key] = "Con " + word
    return out


def _track_key(track):
    words = slug(track).split("-")
    return next((w for w in words if w in TRACK_WORDS), words[0] if words else "")


def key_for(kind, commands, errors=()):
    """The phrase that confirms what was done (None: nothing to say)."""
    if kind == "refused":
        return "refused"
    if kind != "command" or not commands:
        return None
    if errors:
        return "error"
    c = commands[0]
    cmd = c["cmd"]
    if cmd == "goto":
        return "section-" + slug(c["section"])
    if cmd == "song":
        return "song-%d" % c["number"]
    if cmd == "next_is":
        return "next-is-%d" % c["number"]
    if cmd == "skip":
        return "skip-%d" % c["number"]
    if cmd == "mute":
        return ("mute-" if c["on"] else "unmute-") + _track_key(c["track"])
    return cmd if cmd in FIXED else None


# --- rendering (macOS) --------------------------------------------------------------------

def spanish_voice():
    listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    voices = []
    for line in listing.splitlines():
        m = re.match(r"^(.+?)\s{2,}(\w\w_\w+)", line)
        if m:
            voices.append((m.group(1).strip(), m.group(2)))
    for lang in PREFERRED_VOICES:
        for name, code in voices:
            if code == lang:
                return name
    return None


def level(x):
    """Trim silence and bring every phrase to the same level."""
    env = np.abs(x)
    on = np.nonzero(env > 10 ** (-45 / 20))[0]
    if len(on):
        x = x[max(0, on[0] - 480):on[-1] + 2400]
    rms = np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12
    x = x * (10 ** (TARGET_RMS_DB / 20) / rms)
    peak = np.abs(x).max() + 1e-12
    if peak > 10 ** (PEAK_DB / 20):
        x = x * (10 ** (PEAK_DB / 20) / peak)
    return x.astype(np.float32)


def render(folder, voice=None, rate=210):
    import soundfile as sf
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    voice = voice or spanish_voice()
    if voice is None:
        raise SystemExit("No encontré una voz en español de macOS (Ajustes > Accesibilidad > Contenido hablado).")
    phrases = catalog()
    for i, (key, text) in enumerate(sorted(phrases.items()), 1):
        tmp = folder / (key + ".tmp.wav")
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(tmp), "--file-format=WAVE",
                        "--data-format=LEI16@48000", text], check=True)
        x, sr = sf.read(str(tmp), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        sf.write(str(folder / (key + ".wav")), level(x), sr, subtype="PCM_16")
        tmp.unlink()
        print("\r%d/%d %s" % (i, len(phrases), text).ljust(60), end="", flush=True)
    (folder / "voces.json").write_text(json.dumps({"voice": voice, "rate": rate, "phrases": phrases},
                                                  ensure_ascii=False, indent=1))
    print("\nListo: %d frases con la voz %s en %s" % (len(phrases), voice, folder))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--voice", help="Voz de macOS (por defecto, la primera en español: México, Latinoamérica…)")
    ap.add_argument("--rate", type=int, default=210, help="Palabras por minuto")
    args = ap.parse_args(argv)
    render(args.folder, args.voice, args.rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
