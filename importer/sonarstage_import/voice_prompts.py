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
         "next_section": "Siguiente", "next_song": "Siguiente canción", "play": "Play", "stop": "Paramos",
         "refused": "No entendí", "error": "No se pudo", "first_song": "Ya es la primera"}
SONGS = 12
PREFERRED_VOICES = ("es_MX", "es_419", "es_US", "es_ES")
PREFERRED_NAMES = ("Paulina", "Mónica", "Juan", "Jorge")     # clear speaking voices first
# Like the packs' guides: measured on "Alegras mis días", the guide's speech is bright
# (spectral centroid ~3 kHz, 2 % of the energy under 250 Hz) at ~-20 dB RMS; macOS's
# Paulina came out dull (centroid ~1 kHz, ~45 % under 250 Hz). So: low cut, presence and
# air, a little compression, and the level of the guide.
TARGET_RMS_DB = -18.0
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


def key_for(kind, commands, errors=(), state=None):
    """The phrase that confirms what was done (None: nothing to say). With Ableton's reply
    (`state`), a jump is confirmed with the section it will really land on ("Coro dos")."""
    if kind == "refused":
        return "refused"
    if kind != "command" or not commands:
        return None
    if errors:
        return "error"
    c = commands[0]
    cmd = c["cmd"]
    state = state or {}
    if cmd in ("goto", "next_section"):
        name = state.get("pending") or (state.get("section") if cmd == "goto" or not state.get("playing") else None)
        if name and not re.match(r"^\s*\d+\.\s", name):          # a song locator is not a section
            return "section-" + slug(name)
        if cmd == "next_section":
            return "next_section"
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

def spanish_voice(listing=None):
    """First Spanish voice of `say -v ?` (lines like "Paulina (Enhanced)   es_MX   # Hola…")."""
    if listing is None:
        listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    voices = []
    for line in listing.splitlines():
        m = re.search(r"\s(es[_-][A-Za-z0-9]+)\b", line.split("#")[0])
        if m:
            voices.append((line[:m.start()].strip(), m.group(1).replace("-", "_")))
    for lang in PREFERRED_VOICES:
        here = [name for name, code in voices if code == lang]
        for wanted in PREFERRED_NAMES:
            for name in here:
                if name.split(" (")[0] == wanted:
                    return wanted if name.startswith(wanted + " (Español") else name
        if here:
            return here[0]
    return None


def _biquad_peak(f0, gain_db, q, sr):
    a_ = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    b = [1 + al * a_, -2 * np.cos(w), 1 - al * a_]
    a = [1 + al / a_, -2 * np.cos(w), 1 - al / a_]
    return np.array(b) / a[0], np.array(a) / a[0]


def _biquad_high_shelf(f0, gain_db, sr):
    a_ = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    c, s2 = np.cos(w), 2 * np.sqrt(a_) * np.sin(w) / 2 * np.sqrt(2)
    b = [a_ * ((a_ + 1) + (a_ - 1) * c + s2), -2 * a_ * ((a_ - 1) + (a_ + 1) * c), a_ * ((a_ + 1) + (a_ - 1) * c - s2)]
    a = [(a_ + 1) - (a_ - 1) * c + s2, 2 * ((a_ - 1) - (a_ + 1) * c), (a_ + 1) - (a_ - 1) * c - s2]
    return np.array(b) / a[0], np.array(a) / a[0]


def brighten(x, sr):
    """Low cut 300 Hz, +8 dB at 3 kHz, +6 dB shelf from 6 kHz (guide-like voice)."""
    from scipy.signal import butter, lfilter, sosfilt
    x = sosfilt(butter(4, 300, "highpass", fs=sr, output="sos"), x)
    x = lfilter(*_biquad_peak(3000, 8, 0.9, sr), x)
    return lfilter(*_biquad_high_shelf(6000, 6, sr), x)


def compress(x, sr, above_rms_db=8.0, ratio=4.0, threshold=None, attack_s=0.005):
    """Compressor (80 ms release) so peaks ("ción") do not set the level. With `threshold`
    (linear) and a high ratio it is the final limiter."""
    rms = np.sqrt(np.mean(x ** 2)) + 1e-12
    thr = threshold if threshold is not None else rms * 10 ** (above_rms_db / 20)
    env = np.abs(x)
    att, rel = np.exp(-1 / (attack_s * sr)), np.exp(-1 / (0.08 * sr))
    e, out = 0.0, np.empty_like(env)
    for i, v in enumerate(env):
        e = att * e + (1 - att) * v if v > e else rel * e + (1 - rel) * v
        out[i] = e
    gain = np.where(out > thr, (thr / np.maximum(out, 1e-12)) ** (1 - 1 / ratio), 1.0)
    return x * gain


def level(x, sr=48000):
    """Trim silence, make it sound like a guide, and bring every phrase to the same level."""
    x = np.asarray(x, dtype=np.float64)
    env = np.abs(x)
    on = np.nonzero(env > 10 ** (-45 / 20))[0]
    if len(on):
        x = x[max(0, on[0] - 480):on[-1] + 2400]
    x = compress(brighten(x, sr), sr)
    for _ in range(3):                       # level, then limit the few peaks above the ceiling
        rms = np.sqrt(np.mean(x ** 2)) + 1e-12
        x = x * (10 ** (TARGET_RMS_DB / 20) / rms)
        x = compress(x, sr, ratio=20.0, threshold=10 ** ((PEAK_DB - 1) / 20), attack_s=0.0005)
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
        raise SystemExit("No encontré una voz en español de macOS. Instala una en Ajustes del Sistema >\n"
                         "Accesibilidad > Contenido hablado > Voz del sistema > Gestionar voces > Español\n"
                         "(por ejemplo Paulina, México) y vuelve a correr este comando.")
    phrases = catalog()
    for i, (key, text) in enumerate(sorted(phrases.items()), 1):
        tmp = folder / (key + ".tmp.wav")
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(tmp), "--file-format=WAVE",
                        "--data-format=LEI16@48000", text], check=True)
        x, sr = sf.read(str(tmp), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        sf.write(str(folder / (key + ".wav")), level(x, sr), sr, subtype="PCM_16")
        tmp.unlink()
        print(("\r%d/%d %s" % (i, len(phrases), text)).ljust(60), end="", flush=True)
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
