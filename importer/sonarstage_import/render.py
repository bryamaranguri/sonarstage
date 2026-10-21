"""Render a library song into the files a show needs.

    python -m sonarstage_import.render <song folder> --out <dir>
        [--sample-rate 48000] [--live "drums,bass,EG 1"]

Applies the recipe in cancion.json (one gain per stem) and writes WAV at the user's
sample rate, so Ableton neither decodes nor resamples on stage. Files per group:

- CUES: click and guide, one file each.
- EN VIVO: one file per stem the band plays this week (matched by role or by stem
  name), muted in the show and ready to unmute if a musician has a problem.
- SECUENCIA: everything else summed into one stereo file. Those stems are never muted
  separately, so keeping them apart only cost disk space and tracks (a 12-song show
  went from ~18 GB to a fraction of that).

A premixed sequence that came along with separate stems is left out (it is a backup
copy of the same music). Every written file is read back and checked. A show.json
manifest lists the files and their group for the show generator.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from . import printing
from .audio_io import decode

CUE_ROLES = {"click", "guide"}
SEQUENCE_FILE = "Secuencia"


class RenderError(Exception):
    pass


def _is_live(stem, live):
    keys = {stem["role"].lower(), stem["label"].lower()}
    return bool(keys & live)


def _write_checked(path, y, sr):
    """Write 24-bit WAV, or 32-bit float if the signal would clip, then verify it."""
    peak = printing.peak_db(y)
    subtype = "PCM_24" if peak <= printing.STEM_CEILING_DBFS + 0.05 else "FLOAT"
    sf.write(str(path), y.astype(np.float32), sr, subtype=subtype, format="WAV")
    info = sf.info(str(path))
    back, _ = sf.read(str(path), dtype="float32")
    if info.samplerate != sr or info.frames != len(y):
        raise RenderError(f"{path.name}: escrito con tamaño o frecuencia inesperados.")
    if abs(printing.peak_db(back) - peak) > 0.1:
        raise RenderError(f"{path.name}: el contenido no coincide con lo esperado.")
    return {"file": path.name, "frames": info.frames, "peak_db": round(peak, 1), "subtype": subtype}


def render_song(song_dir, out_dir, sample_rate=48000, live=(), semitones=0):
    song_dir, out_dir = Path(song_dir), Path(out_dir)
    song = json.loads((song_dir / "cancion.json").read_text())
    if semitones:
        if not (song_dir / "preparada" / f"{semitones:+d}").exists():
            raise RenderError(f"No hay versión impresa en {semitones:+d} semitonos (cambio de tono pendiente).")
    live = {x.strip().lower() for x in live if x.strip()}
    out_dir.mkdir(parents=True, exist_ok=True)

    stems = song["stems"]
    has_separate_music = any(s["role"] not in CUE_ROLES | {"premix"} for s in stems)
    files, sequence, sequence_labels, skipped = [], None, [], []

    for stem in stems:
        if stem["role"] == "premix" and has_separate_music:
            skipped.append(stem["label"])
            continue
        x = decode(song_dir / "originales" / stem["file"], sample_rate) * printing.db_to_gain(stem["gainDb"])
        if stem["role"] in CUE_ROLES:
            files.append({**_write_checked(out_dir / f"{stem['label']}.wav", x, sample_rate),
                          "group": "CUES", "role": stem["role"], "label": stem["label"]})
        elif _is_live(stem, live):
            files.append({**_write_checked(out_dir / f"{stem['label']}.wav", x, sample_rate),
                          "group": "EN VIVO", "role": stem["role"], "label": stem["label"]})
        else:
            if sequence is None:
                sequence = x.astype(np.float64)
            else:
                n = min(len(sequence), len(x))
                sequence = sequence[:n] + x[:n]
            sequence_labels.append(stem["label"])
        del x

    if sequence is not None:
        files.append({**_write_checked(out_dir / f"{SEQUENCE_FILE}.wav", sequence, sample_rate),
                      "group": "SECUENCIA", "role": "sequence", "label": SEQUENCE_FILE,
                      "contains": sequence_labels})

    unmatched = sorted(live - {k for s in stems for k in (s["role"].lower(), s["label"].lower())})
    manifest = {
        "song": song["title"], "id": song["id"], "sample_rate": sample_rate,
        "tempo": song["tempo"], "sections": song["sections"],
        "live": sorted(live), "live_not_in_song": unmatched, "skipped": skipped,
        "files": files,
    }
    (out_dir / "show.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-rate", type=int, default=48000)
    ap.add_argument("--live", default="", help="Roles o stems que toca la banda, separados por comas")
    args = ap.parse_args(argv)
    try:
        m = render_song(args.song, args.out, args.sample_rate, args.live.split(","))
    except RenderError as e:
        print(f"No se pudo renderizar: {e}", file=sys.stderr)
        return 1
    groups = {}
    for f in m["files"]:
        groups.setdefault(f["group"], []).append(f["label"])
    print(f"{m['song']} a {m['sample_rate']} Hz:")
    for g in ("CUES", "EN VIVO", "SECUENCIA"):
        if g in groups:
            extra = f" (suma de {len(m['files'][-1]['contains'])} stems)" if g == "SECUENCIA" else ""
            print(f"  {g:9} {', '.join(groups[g])}{extra}")
    if m["live_not_in_song"]:
        print(f"  ⚠ No hay stems para: {', '.join(m['live_not_in_song'])}")
    if m["skipped"]:
        print(f"  Premezcla omitida (hay stems separados): {', '.join(m['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
