"""Render a library song into playable WAV files for a show.

    python -m sonarstage_import.render <song folder> --out <dir> [--sample-rate 48000]

Applies the recipe in cancion.json (one gain per stem) to the originals and writes
24-bit WAV at the user's sample rate (the one their interface runs at), so Ableton
neither decodes nor resamples anything on stage. Each written file is read back and
checked.
"""
import argparse
import json
import sys
from pathlib import Path

import soundfile as sf

from . import printing
from .audio_io import decode


class RenderError(Exception):
    pass


def render_song(song_dir, out_dir, sample_rate=48000, semitones=0):
    song_dir, out_dir = Path(song_dir), Path(out_dir)
    song = json.loads((song_dir / "cancion.json").read_text())
    if semitones:
        prepared = song_dir / "preparada" / f"{semitones:+d}"
        if not prepared.exists():
            raise RenderError(f"No hay versión impresa en {semitones:+d} semitonos (cambio de tono pendiente).")
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for stem in song["stems"]:
        source = song_dir / "originales" / stem["file"]
        x = decode(source, sample_rate)
        target = out_dir / f"{stem['label']}.wav"
        printing.write_stem(target, x, sample_rate, stem["gainDb"], fmt="WAV")
        expected_frames = len(x)
        expected_peak = printing.peak_db(x * printing.db_to_gain(stem["gainDb"]))
        info = sf.info(str(target))
        y, _ = sf.read(str(target), dtype="float32")
        if info.samplerate != sample_rate or info.frames != expected_frames:
            raise RenderError(f"{target.name}: escrito con tamaño o frecuencia inesperados.")
        if abs(printing.peak_db(y) - expected_peak) > 0.1:
            raise RenderError(f"{target.name}: el contenido no coincide con lo esperado.")
        written.append({"file": target.name, "role": stem["role"], "label": stem["label"],
                        "frames": info.frames, "peak_db": round(printing.peak_db(y), 1)})
    return {"song": song["title"], "sample_rate": sample_rate, "files": written}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-rate", type=int, default=48000)
    args = ap.parse_args(argv)
    try:
        result = render_song(args.song, args.out, args.sample_rate)
    except RenderError as e:
        print(f"No se pudo renderizar: {e}", file=sys.stderr)
        return 1
    print(f"{result['song']}: {len(result['files'])} archivos WAV a {result['sample_rate']} Hz en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
