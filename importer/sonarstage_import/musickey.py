"""Musical key: names, transposition and an estimate from the harmonic stems.

The estimate sums a pitch-class profile (chroma) over the harmonic stems (bass, guitars,
keys, pads; not drums, click, guide or vocals) and correlates it with the 24 key
profiles of Albrecht & Shanahan (2013), measured on pop/rock, which suits worship music
better than the classical Krumhansl profiles. The bass counts double: it sits on the root.

It is a suggestion. Relative keys (G / Em) and songs that lean on IV are the usual
misses, so the user confirms it once in the library and the confirmed key wins.

    python -m sonarstage_import.musickey <song folder> [...]     # print the estimate
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

# how musicians write them (letters, the usual spelling for each key)
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

MAJOR_PROFILE = np.array([0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081])
MINOR_PROFILE = np.array([0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052])

KEY_ROLES = {"bass", "eg", "ag", "keys", "piano", "organ", "synth", "pad", "strings"}
SR = 11025


class KeyError_(ValueError):
    pass


def parse(name):
    """'G' → (7, False); 'F#m' → (6, True); 'Bb' / 'A#' / 'Sib'? no: letters only."""
    s = (name or "").strip()
    if not s or s[0].upper() not in _LETTERS:
        raise KeyError_("Tono no válido: %r" % name)
    pc = _LETTERS[s[0].upper()]
    rest = s[1:]
    while rest[:1] in ("#", "♯", "b", "♭"):
        pc += 1 if rest[0] in "#♯" else -1
        rest = rest[1:]
    if rest not in ("", "m", "min"):
        raise KeyError_("Tono no válido: %r" % name)
    return pc % 12, rest != ""


def name(pc, minor):
    return (MINOR_NAMES if minor else MAJOR_NAMES)[pc % 12]


def normalize(key):
    """Canonical spelling ('A#' → 'Bb'), or None for unknown ('?', '', None)."""
    if not key or key == "?":
        return None
    return name(*parse(key))


def transpose(key, semitones):
    """'G', +2 → 'A'. Unknown key → None."""
    k = normalize(key)
    if k is None:
        return None
    pc, minor = parse(k)
    return name(pc + int(semitones), minor)


def chroma(x, sr=SR, frame=8192, hop=4096, fmin=50.0, fmax=2500.0):
    """Mean pitch-class profile of a mono signal; every sounding frame weighs the same."""
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if len(x) < frame:
        return np.zeros(12)
    freqs = np.fft.rfftfreq(frame, 1.0 / sr)
    band = (freqs >= fmin) & (freqs <= fmax)
    pcs = (np.round(69 + 12 * np.log2(freqs[band] / 440.0)).astype(int)) % 12
    onehot = np.zeros((band.sum(), 12))
    onehot[np.arange(band.sum()), pcs] = 1.0
    win = np.hanning(frame).astype(np.float32)
    n = 1 + (len(x) - frame) // hop
    total, energies, frames = np.zeros(12), [], []
    for i in range(n):
        seg = x[i * hop:i * hop + frame] * win
        mag = np.abs(np.fft.rfft(seg))[band]
        c = mag @ onehot
        frames.append(c)
        energies.append(c.sum())
    energies = np.array(energies)
    if not len(energies) or energies.max() <= 0:
        return np.zeros(12)
    loud = energies > energies.max() * 0.05            # skip the silent stretches
    for c, e, ok in zip(frames, energies, loud):
        if ok:
            total += c / e
    return total / max(1, loud.sum())


def scores(profile):
    """[(name, correlation)] for the 24 keys, best first."""
    p = np.asarray(profile, dtype=float)
    if not np.any(p):
        return []
    out = []
    for minor, ref in ((False, MAJOR_PROFILE), (True, MINOR_PROFILE)):
        for pc in range(12):
            out.append((name(pc, minor), float(np.corrcoef(p, np.roll(ref, pc))[0, 1])))
    return sorted(out, key=lambda t: -t[1])


def estimate_from_profile(profile):
    s = scores(profile)
    if not s:
        return None
    return {"key": s[0][0], "confidence": round(s[0][1] - s[1][1], 3),
            "candidates": [k for k, _ in s[:3]]}


def estimate(stems, decode=None):
    """stems: [(role, path)]. Returns {"key", "confidence", "candidates"} or None."""
    if decode is None:
        from .audio_io import decode
    total = np.zeros(12)
    for role, path in stems:
        if role not in KEY_ROLES:
            continue
        c = chroma(decode(path, SR, mono=True)[:, 0])
        if c.any():
            total += (2.0 if role == "bass" else 1.0) * c / c.sum()
    return estimate_from_profile(total)


def estimate_song(song_dir):
    song_dir = Path(song_dir)
    song = json.loads((song_dir / "cancion.json").read_text())
    return estimate([(s["role"], song_dir / "originales" / s["file"]) for s in song["stems"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Estimar la tonalidad de canciones de la biblioteca")
    ap.add_argument("songs", nargs="+")
    a = ap.parse_args(argv)
    for d in a.songs:
        r = estimate_song(d)
        print("%-30s %s" % (Path(d).name, "—" if r is None else "%s  (margen %.3f; también %s)"
                            % (r["key"], r["confidence"], ", ".join(r["candidates"][1:]))))


if __name__ == "__main__":
    sys.exit(main())
