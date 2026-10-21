"""Prepare a show: render every song and write the Ableton Live set.

    python -m sonarstage_import.show <library> --out <show folder> --template <set.als>
        --songs "Holy Forever:-2" "Alegras mis días" [--band <banda.json>] [--presentes ...]
        [--profile 2] [--gap 30] [--sample-rate 48000] [--real-path LOCAL=REAL]

Each song is "Title" or "Title:semitones" (the transposed version must exist). The show
folder gets Audio/<nn> <Title>/ with the WAVs of each song, show.json, and
<folder name>.als, ready to open in Ableton. Nothing in the library is modified.
"""
import argparse
import json
import sys
from pathlib import Path

from . import ableton, parts
from .render import RenderError, render_song

CUE_LANES = {"click": "Click", "guide": "Guía"}


def parse_song(spec):
    title, _, semis = spec.rpartition(":")
    if title and semis.lstrip("+-").isdigit():
        return title, int(semis)
    return spec, 0


def prepare_show(library, out_dir, template, song_specs, band=None, present=None, profile="2",
                 gap_seconds=30.0, sample_rate=48000, path_map=None):
    library, out_dir = Path(library), Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ableton.AlsError(f"La carpeta del show ya existe y no está vacía: {out_dir}")
    songs, report = [], []
    for n, spec in enumerate(song_specs, 1):
        title, semis = parse_song(spec)
        song_dir = library / title
        if not (song_dir / "cancion.json").exists():
            raise ableton.AlsError(f"No está en la biblioteca: {title}")
        audio_dir = out_dir / "Audio" / f"{n:02d} {title}"
        manifest = render_song(song_dir, audio_dir, sample_rate, (), semis, band, present)
        # every source names its cues differently (Click Track, Cues, Guide…): one lane per role
        files = [{"group": f["group"], "label": CUE_LANES.get(f["role"], f["label"]),
                  "path": str(audio_dir / f["file"]), "frames": f["frames"], "sr": sample_rate}
                 for f in manifest["files"]]
        songs.append({"title": title, "tempo": manifest["tempo"], "sections": manifest["sections"],
                      "duration_s": max(f["frames"] for f in files) / sample_rate, "files": files,
                      "semitones": semis})
        report.append({"title": title, "semitones": semis, "warnings": manifest["warnings"],
                       "files": [(f["group"], f["label"]) for f in manifest["files"]]})
    als = out_dir / f"{out_dir.name}.als"
    result = ableton.build_set(template, songs, als, profile, gap_seconds, path_map)
    (out_dir / "show.json").write_text(json.dumps({
        "songs": report, "profile": profile, "gap_seconds": gap_seconds, "sample_rate": sample_rate,
        "band": band["id"] if band else None, "present": present, "als": als.name,
        "live_version": result["version"], "starts_beats": result["starts"]}, indent=1, ensure_ascii=False))
    return result, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("library")
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--songs", nargs="+", required=True)
    ap.add_argument("--band")
    ap.add_argument("--presentes")
    ap.add_argument("--profile", default="2", choices=sorted(ableton.PROFILES))
    ap.add_argument("--gap", type=float, default=30.0, help="Segundos entre canciones")
    ap.add_argument("--sample-rate", type=int, default=48000)
    ap.add_argument("--real-path", help="LOCAL=REAL: prefijo de ruta a reescribir para la Mac")
    args = ap.parse_args(argv)
    try:
        band = parts.load_band(args.band) if args.band else None
        present = args.presentes.split(",") if args.presentes else None
        path_map = tuple(args.real_path.split("=", 1)) if args.real_path else None
        result, report = prepare_show(args.library, args.out, args.template, args.songs, band, present,
                                      args.profile, args.gap, args.sample_rate, path_map)
    except (ableton.AlsError, RenderError, parts.PartsError) as e:
        print(f"No se pudo preparar el show: {e}", file=sys.stderr)
        return 1
    print(f"Show listo: {result['als']}  (formato de {result['version']})")
    for r, start in zip(report, result["starts"]):
        tono = f" en {r['semitones']:+d}" if r["semitones"] else ""
        print(f"  compás {int(start // 4) + 1:>4}: {r['title']}{tono}")
        for w in r["warnings"]:
            print(f"        ⚠ {w}")
    print(f"  Pistas: {', '.join(f'{g}/{l}' for g, l in result['tracks'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
