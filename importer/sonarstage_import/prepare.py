"""Import a stem pack into the library: extract, analyse and store the recipe.

    python -m sonarstage_import.prepare <pack.zip|pack.rar|folder> --library <dir>
        [--title "Nombre"] [--target-lufs -18] [--offsets offsets.json]

Writes <library>/<title>/ with originales/ (as they came), cancion.json (the recipe:
roles, gains, tempo, sections) and analisis.json. No audio is printed here: gains are
applied when a show is prepared (see render.py), which takes seconds per song. Only
transposed versions, which are slow to compute, will be stored under preparada/<tono>/.
Never touches the source pack and refuses to overwrite a song.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import library, printing
from .analyze import analyze, print_summary
from .audio_io import decode
from .extract import PackError, extract_pack


def prepare(source, library_dir, title=None, target_lufs=printing.TARGET_LUFS, offsets_db=None, quiet=False):
    source = Path(source)
    title = title or library.title_from_source(source.name)
    song_dir = Path(library_dir) / title
    if song_dir.exists():
        raise PackError(f"Ya existe en la biblioteca: {song_dir}")
    originals = song_dir / "originales"
    extract_pack(source, originals)

    report = analyze(originals, target_lufs)
    if not quiet:
        print_summary(report)
    if "tempo" not in report:
        raise PackError("Sin click no se puede preparar automáticamente (falta tempo y compases).")

    # Gains are measured at the source sample rate; conversion to each user's rate
    # happens when the show is rendered.
    sr = Counter(s["sample_rate"] for s in report["stems"]).most_common(1)[0][0]
    stems = report["stems"]
    music = [s for s in stems if s["role"] not in printing.CUE_ROLES]

    measured = printing.measure_mix(
        ((s["role"], decode(originals / s["file"], sr)) for s in music), sr, offsets_db)
    song_gain, limited_by = printing.plan_song_gain(
        measured["lufs"], measured["peak_db"], measured["stem_peaks_db"], target_lufs)

    song_stems, used_names = [], set()
    for s in stems:
        if s["role"] in printing.CUE_ROLES:
            gain = printing.plan_cue_gain(s["role"], s["levels"]["lufs"], s["levels"]["peak_dbfs"])
        else:
            gain = round(song_gain + (offsets_db or {}).get(s["role"], 0.0), 2)
        name = s["label"]
        while name.lower() in used_names:
            name += " b"
        used_names.add(name.lower())
        song_stems.append({
            "file": s["file"], "role": s["role"], "label": name, "harmonic": s["harmonic"],
            "gainDb": gain, "offsetMs": 0, "monoSafe": s["levels"]["mono_safe"],
            "sourceFormat": f"{s['codec']} {s['bitrate_kbps']} kbps" if s["bitrate_kbps"] else s["codec"],
        })

    t = report["tempo"]
    meter = report.get("meter", {"beats_per_bar": 4, "downbeat_phase": 0})
    first_down = t["first_beat_s"] + meter["downbeat_phase"] * 60 / t["bpm"]
    duration = max(s["duration_s"] or 0 for s in stems)
    bars = library.total_bars(duration, t["bpm"], first_down, meter["beats_per_bar"])
    sections = library.sections_from_cues(report.get("guide_cues", []), bars)

    song = library.build_song_json(
        song_id=library.slugify(title), title=title, source=source.name, report=report,
        stems=song_stems, sections=sections, target_lufs=target_lufs, prepared_semitones=())
    error = library.validate(song)
    if error:
        raise PackError(f"cancion.json no cumple el esquema: {error}")
    (song_dir / "cancion.json").write_text(json.dumps(song, indent=1, ensure_ascii=False))
    report["printing"] = {"sample_rate": sr, "song_gain_db": song_gain, "limited_by": limited_by,
                          "mix_before": {"lufs": round(measured["lufs"], 1), "peak_db": round(measured["peak_db"], 1)}}
    (song_dir / "analisis.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))

    if not quiet:
        expected_lufs = measured["lufs"] + song_gain
        print(f"\nEn la biblioteca: {song_dir}")
        print(f"Ganancia de la canción: {song_gain:+} dB (limitada por {limited_by}) "
              f"→ mezcla esperada {expected_lufs:.1f} LUFS, pico {measured['peak_db'] + song_gain:.1f} dBFS")
        print(f"Secciones provisionales: {len(sections)} · {bars} compases")
    return song_dir, song, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--library", required=True)
    ap.add_argument("--title")
    ap.add_argument("--target-lufs", type=float, default=printing.TARGET_LUFS)
    ap.add_argument("--offsets", help="JSON con ajustes por rol en dB, p. ej. {\"pad\": -2}")
    args = ap.parse_args(argv)
    offsets = json.loads(Path(args.offsets).read_text()) if args.offsets else None
    try:
        prepare(args.source, args.library, args.title, args.target_lufs, offsets)
    except PackError as e:
        print(f"No se pudo preparar: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
