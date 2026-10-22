"""Print transposed versions of a library song.

    python -m sonarstage_import.transpose <song folder> --semitones -2

Only harmonic stems change key (bass, guitars, keys, pads, strings, vocals, FX).
Click, guide, drums and percussion stay as they are. Pitch shifting uses the Rubber
Band command-line tool (v3 or newer) with its R3 "finer" engine in offline mode: the
whole file is studied before processing, which gives the library's highest quality.
ffmpeg's rubberband filter is not used because it only offers the older R2 engine and
always runs in real-time mode. Vocals keep their formants so they do not sound
"chipmunk" or "giant". Stereo stems use centre focus (keeps mono compatibility).

The tool is found through $SONARSTAGE_RUBBERBAND or the PATH (on the Mac,
`brew install rubberband`; the app bundles it next to ffmpeg).

Output: <song>/preparada/<n>/<label>.flac (24-bit, source sample rate, no gain: the
recipe in cancion.json still applies at render time).

Timing: offline mode already compensates the shifter's latency, but any residual
offset is measured once per song on a synthetic tone-burst signal with the same
settings and compensated in every stem; the length is restored exactly.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from . import library, printing
from .audio_io import decode, probe

FORMANT_PRESERVED = {"leadVocal", "choir"}
CUE_ROLES = {"click", "guide"}
MAX_SEMITONES = 6          # schema limit; beyond ±3 artefacts become audible
QUALITY_WARNING = 3


class TransposeError(Exception):
    pass


MIN_RUBBERBAND_MAJOR = 3    # R3 ("finer") engine


def rubberband_tool():
    """Path of the rubberband command-line tool, or None."""
    return os.environ.get("SONARSTAGE_RUBBERBAND") or shutil.which("rubberband")


def rubberband_version():
    tool = rubberband_tool()
    if not tool:
        return None
    try:
        out = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out.stdout + out.stderr)
    return tuple(int(g) for g in m.groups()) if m else None


def rubberband_available():
    v = rubberband_version()
    return v is not None and v[0] >= MIN_RUBBERBAND_MAJOR


def rubberband_args(semitones, role):
    args = ["--fine", "--pitch", str(semitones), "--centre-focus", "--ignore-clipping", "--quiet"]
    if role in FORMANT_PRESERVED:
        args.append("--formant")
    return args


def _shift_audio(x, semitones, role, sample_rate):
    """Pitch-shift float32 audio (frames, 2) offline with the R3 engine; returns float32 (frames, 2)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.wav"), os.path.join(tmp, "out.wav")
        sf.write(src, x, sample_rate, subtype="FLOAT")
        subprocess.run([rubberband_tool(), *rubberband_args(semitones, role), src, dst],
                       capture_output=True, check=True)
        y, sr = sf.read(dst, dtype="float32", always_2d=True)
    if sr != sample_rate or y.shape[1] != 2:
        raise TransposeError("Rubber Band devolvió un formato inesperado.")
    return y


def _burst_signal(sample_rate, seconds=12):
    """Tone bursts with sharp, known on/off times (a click would change shape when shifted)."""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    gate = ((t % 0.5) < 0.15).astype(np.float32)
    ramp = max(1, int(0.001 * sample_rate))
    gate = np.convolve(gate, np.ones(ramp) / ramp, mode="same")
    x = (0.4 * np.sin(2 * np.pi * 330 * t) * gate).astype(np.float32)
    return np.stack([x, x], axis=1)


def _envelope(x, sample_rate, hop_s=0.0001):
    h = max(1, int(hop_s * sample_rate))
    m = x[:, 0] ** 2
    n = len(m) // h
    e = np.sqrt(m[:n * h].reshape(n, h).mean(axis=1))
    w = int(0.003 / hop_s)
    e = np.convolve(e, np.ones(w) / w, mode="same")
    return e - e.mean()


def measure_offset_samples(semitones, sample_rate):
    """Delay (in samples, positive = late) that the pitch shifter adds at these settings."""
    x = _burst_signal(sample_rate)
    y = _shift_audio(x, semitones, "keys", sample_rate)
    return int(round(burst_lag_ms(x, y, sample_rate) / 1000 * sample_rate))


def burst_lag_ms(x, y, sample_rate):
    """Lag of y relative to x (ms, 0.1 ms resolution, positive = late) for burst signals."""
    ex, ey = _envelope(x, sample_rate), _envelope(y, sample_rate)
    n = min(len(ex), len(ey))
    size = 1 << int(np.ceil(np.log2(2 * n)))
    xc = np.fft.irfft(np.fft.rfft(ex[:n], size) * np.conj(np.fft.rfft(ey[:n], size)), size)
    steps = 500                                      # ±50 ms in 0.1 ms steps
    window = np.concatenate([xc[-steps:], xc[:steps + 1]])
    return -(int(np.argmax(window)) - steps) / 10


def _align(y, offset, length):
    """Undo the shifter's delay and restore the exact original length."""
    if offset > 0:
        y = y[offset:]
    elif offset < 0:
        y = np.concatenate([np.zeros((-offset, 2), dtype=y.dtype), y])
    if len(y) < length:
        y = np.concatenate([y, np.zeros((length - len(y), 2), dtype=y.dtype)])
    return y[:length]


def _shift_one(src, dst, semitones, role, sample_rate, offset):
    x = decode(src, sample_rate)          # ffmpeg decode: honours MP3/AAC encoder delay
    y = _align(_shift_audio(x, semitones, role, sample_rate), offset, len(x))
    length = len(x)
    sf.write(str(dst), y, sample_rate, subtype="PCM_24", format="FLAC")
    if sf.info(str(dst)).frames != length:
        raise TransposeError(f"{dst.name}: la duración no coincide con el original.")
    return dst


def loudness_correction(song_dir, song, semitones, sample_rate):
    """Gain (dB) for every music stem so the transposed mix keeps the song's loudness.

    Shifting down removes some brightness and the mix measures quieter (-0.4 to -0.8 LU
    on real songs at +1/-2). The same correction goes to all music stems, transposed or
    not, so the balance stays as in the recipe; the peak ceiling still applies.
    """
    prepared_dir = song_dir / "preparada" / f"{semitones:+d}"
    music = [s for s in song["stems"] if s["role"] not in CUE_ROLES and s["role"] != "premix"]

    def stems():
        for s in music:
            src = prepared_dir / f"{s['label']}.flac" if s["harmonic"] else song_dir / "originales" / s["file"]
            yield s["role"], decode(src, sample_rate) * printing.db_to_gain(s["gainDb"])

    m = printing.measure_mix(stems(), sample_rate)
    target = song.get("mix", {}).get("targetLufs", printing.TARGET_LUFS)
    gain, _ = printing.plan_song_gain(m["lufs"], m["peak_db"], m["stem_peaks_db"], target)
    return gain


def transpose_song(song_dir, semitones, workers=4):
    song_dir = Path(song_dir)
    if semitones == 0:
        raise TransposeError("0 semitonos es el tono original: no hace falta imprimir nada.")
    if abs(semitones) > MAX_SEMITONES:
        raise TransposeError(f"Máximo ±{MAX_SEMITONES} semitonos.")
    if not rubberband_available():
        raise TransposeError("Falta Rubber Band 3 o más reciente (motor R3) para cambiar el tono.")
    song = json.loads((song_dir / "cancion.json").read_text())
    out_dir = song_dir / "preparada" / f"{semitones:+d}"
    if out_dir.exists():
        raise TransposeError(f"Ya existe la versión en {semitones:+d} semitonos.")
    harmonic = [s for s in song["stems"] if s["harmonic"]]
    sample_rate = probe(song_dir / "originales" / harmonic[0]["file"])["sample_rate"] if harmonic else 44100

    offset = measure_offset_samples(semitones, sample_rate)
    tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=False)
    jobs = [(song_dir / "originales" / s["file"], tmp_dir / f"{s['label']}.flac", semitones, s["role"],
             sample_rate, offset) for s in harmonic]
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:      # each job is an ffmpeg process
            list(pool.map(lambda j: _shift_one(*j), jobs))
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    tmp_dir.rename(out_dir)          # appears complete or not at all

    correction = loudness_correction(song_dir, song, semitones, sample_rate)
    key = song.setdefault("key", {"original": "?"})
    key["prepared"] = sorted(set(key.get("prepared", [])) | {semitones})
    key.setdefault("gainCorrectionDb", {})[f"{semitones:+d}"] = correction
    error = library.validate(song)
    if error:
        raise TransposeError(f"cancion.json no cumple el esquema: {error}")
    (song_dir / "cancion.json").write_text(json.dumps(song, indent=1, ensure_ascii=False))
    return {"song": song["title"], "semitones": semitones, "stems": [s["label"] for s in harmonic],
            "offset_ms": round(offset / sample_rate * 1000, 1), "gain_correction_db": correction,
            "untouched": [s["label"] for s in song["stems"] if not s["harmonic"]], "dir": str(out_dir)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("--semitones", type=int, required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    try:
        r = transpose_song(args.song, args.semitones, args.workers)
    except (TransposeError, subprocess.CalledProcessError) as e:
        print(f"No se pudo cambiar el tono: {e}", file=sys.stderr)
        return 1
    print(f"{r['song']} en {r['semitones']:+d} semitonos: {len(r['stems'])} stems transpuestos"
          f" (desfase compensado: {r['offset_ms']:+} ms; ajuste de volumen: {r['gain_correction_db']:+} dB)")
    print(f"  Sin cambio: {', '.join(r['untouched'])}")
    if abs(args.semitones) > QUALITY_WARNING:
        print(f"  ⚠ Más de {QUALITY_WARNING} semitonos: revisa la calidad, pueden notarse artefactos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
