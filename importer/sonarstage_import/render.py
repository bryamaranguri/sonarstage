"""Render a library song into the files a show needs.

    python -m sonarstage_import.render <song folder> --out <dir> --band <banda.json>
        [--presentes bateria,bajo,guitarra] [--sample-rate 48000] [--semitones -2]
    python -m sonarstage_import.render <song folder> --out <dir> --live "drums,EG 1"   (simple)

Applies the recipe in cancion.json (one gain per stem) and writes WAV at the user's
sample rate, so Ableton neither decodes nor resamples on stage. Files per group:

- CUES: click and guide, one file each.
- EN VIVO: one file per musician present this week, with exactly the stems they cover
  in each section (parts matrix, see parts.py), muted in the show and ready to unmute
  if that musician has a problem. With --live instead of a band, one file per stem.
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

from . import parts, printing
from .audio_io import decode

CUE_ROLES = {"click", "guide"}
SEQUENCE_FILE = "Secuencia"


class RenderError(Exception):
    pass


def _simple_coverage(stems, live):
    """--live "drums,EG 1": every matching stem is its own 'musician' for the whole song."""
    wanted = {x.strip().lower() for x in live if x.strip()}
    cov = [{"id": st["label"].lower(), "name": st["label"], "stems": {st["label"]: None}}
           for st in stems if st["role"] not in CUE_ROLES and {st["role"].lower(), st["label"].lower()} & wanted]
    found = {k for st in stems for k in (st["role"].lower(), st["label"].lower())}
    return cov, [f"No hay stems para: {w}" for w in sorted(wanted - found)]


def _safe_filename(name):
    return "".join(c if c not in '/\\:*?"<>|' else "-" for c in name).strip() or "pista"


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


def render_song(song_dir, out_dir, sample_rate=48000, live=(), semitones=0, band=None, present=None):
    song_dir, out_dir = Path(song_dir), Path(out_dir)
    song = json.loads((song_dir / "cancion.json").read_text())
    prepared_dir = song_dir / "preparada" / f"{semitones:+d}"
    if semitones and not prepared_dir.exists():
        raise RenderError(f"No hay versión en {semitones:+d} semitonos: créala primero con transpose.")
    if band is not None and any(x.strip() for x in live):
        raise RenderError("Usa la banda o --live, no los dos.")
    stems = song["stems"]
    try:
        cov, warnings = (parts.coverage(song, band, present) if band is not None
                         else _simple_coverage(stems, live))
    except parts.PartsError as e:
        raise RenderError(str(e)) from e
    out_dir.mkdir(parents=True, exist_ok=True)

    has_separate_music = any(s["role"] not in CUE_ROLES | {"premix"} for s in stems)
    files, skipped = [], []
    sequence, sequence_labels = None, []
    live_audio = {r["id"]: None for r in cov}

    def add(acc, y):
        if acc is None:
            return y.astype(np.float32).copy()
        n = min(len(acc), len(y))
        acc = acc[:n]
        acc += y[:n]
        return acc

    for stem in stems:
        if stem["role"] == "premix" and has_separate_music:
            skipped.append(stem["label"])
            continue
        # transposed harmonic stems come from preparada/<n>/; click, guide and drums never change key
        source = (prepared_dir / f"{stem['label']}.flac" if semitones and stem["harmonic"]
                  else song_dir / "originales" / stem["file"])
        if not source.exists():
            raise RenderError(f"Falta {source.name} en la versión {semitones:+d}.")
        gain = stem["gainDb"]
        if semitones and stem["role"] not in CUE_ROLES:
            gain += song.get("key", {}).get("gainCorrectionDb", {}).get(f"{semitones:+d}", 0.0)
        x = (decode(source, sample_rate) * printing.db_to_gain(gain)).astype(np.float32)
        if stem["role"] in CUE_ROLES:
            files.append({**_write_checked(out_dir / f"{_safe_filename(stem['label'])}.wav", x, sample_rate),
                          "group": "CUES", "role": stem["role"], "label": stem["label"]})
            continue

        # split the stem between the musicians who cover it and the sequence
        rest = np.ones(len(x), dtype=np.float32)
        bounds = None
        for r in cov:
            if stem["label"] not in r["stems"]:
                continue
            secs = r["stems"][stem["label"]]
            if secs is None:
                m = np.ones(len(x), dtype=np.float32)
            else:
                bounds = bounds or parts.section_bounds(song, len(x), sample_rate)
                m = parts.mask(len(x), bounds, secs, sample_rate)
            live_audio[r["id"]] = add(live_audio[r["id"]], x * m[:, None])
            rest -= m
        if rest.max() > 1e-6:
            sequence = add(sequence, x * np.clip(rest, 0, 1)[:, None])
            sequence_labels.append(stem["label"])
        del x, rest

    live_files = []
    for r in cov:
        audio = live_audio[r["id"]]
        if audio is None:
            continue
        info = _write_checked(out_dir / f"{_safe_filename(r['name'])}.wav", audio, sample_rate)
        live_files.append({**info, "group": "EN VIVO", "role": "live", "label": r["name"], "musician": r["id"],
                           "contains": {lab: ("todo" if secs is None else sorted(secs))
                                        for lab, secs in r["stems"].items()}})
    files.extend(live_files)
    if sequence is not None:
        files.append({**_write_checked(out_dir / f"{SEQUENCE_FILE}.wav", sequence, sample_rate),
                      "group": "SECUENCIA", "role": "sequence", "label": SEQUENCE_FILE,
                      "contains": sequence_labels})

    manifest = {
        "song": song["title"], "id": song["id"], "sample_rate": sample_rate, "semitones": semitones,
        "tempo": song["tempo"], "sections": song["sections"],
        "band": band["id"] if band is not None else None,
        "present": [r["id"] for r in cov], "warnings": warnings, "skipped": skipped,
        "files": files,
    }
    (out_dir / "show.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-rate", type=int, default=48000)
    ap.add_argument("--band", help="Archivo de la banda (banda.json)")
    ap.add_argument("--presentes", help="Músicos que tocan esta semana, separados por comas (por defecto, todos)")
    ap.add_argument("--live", default="", help="Modo simple: roles o stems en vivo, separados por comas")
    ap.add_argument("--semitones", type=int, default=0, help="Versión transpuesta a usar (debe existir)")
    args = ap.parse_args(argv)
    try:
        band = parts.load_band(args.band) if args.band else None
        present = args.presentes.split(",") if args.presentes else None
        m = render_song(args.song, args.out, args.sample_rate, args.live.split(","), args.semitones, band, present)
    except (RenderError, parts.PartsError) as e:
        print(f"No se pudo renderizar: {e}", file=sys.stderr)
        return 1
    groups = {}
    for f in m["files"]:
        groups.setdefault(f["group"], []).append(f["label"])
    tono = f", {m['semitones']:+d} semitonos" if m["semitones"] else ""
    print(f"{m['song']} a {m['sample_rate']} Hz{tono}:")
    for g in ("CUES", "EN VIVO", "SECUENCIA"):
        if g in groups:
            extra = f" (suma de {len(m['files'][-1]['contains'])} stems)" if g == "SECUENCIA" else ""
            print(f"  {g:9} {', '.join(groups[g])}{extra}")
    for w in m["warnings"]:
        print(f"  ⚠ {w}")
    if m["skipped"]:
        print(f"  Premezcla omitida (hay stems separados): {', '.join(m['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
