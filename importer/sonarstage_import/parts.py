"""Bands, the weekly lineup and the parts matrix.

    python -m sonarstage_import.parts grid <song> [--role eg]
    python -m sonarstage_import.parts show <song> --band <banda.json>
    python -m sonarstage_import.parts set <song> --band <banda.json> --musician guitarra --secciones "3=EG 1" "4,5=EG 2+EG 3"
    python -m sonarstage_import.parts set <song> --band <banda.json> --musician guitarra --whole "EG 1"
    python -m sonarstage_import.parts clear <song> --band <banda.json> --musician guitarra
    python -m sonarstage_import.parts pickup <song> 6 1        (sección 6 empieza 1 tiempo antes)

A band (shared/banda.schema.json) lists its musicians, each with the stems they cover
by default. For a song, a musician can instead have a matrix: per section, which
stems they play (EG 1 in the intro, EG 2 + EG 3 in the chorus…). Sections are referred
to by their number in `grid`; they are stored by their first bar.

At render time each present musician gets one EN VIVO file with exactly what they
cover, section by section, and everything else goes to SECUENCIA. The two always add
up to the full song, so unmuting a musician's file fills in exactly what they play.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from . import grid, printing
from .audio_io import decode

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "shared"
RAMP_S = 0.010          # crossfade at section boundaries (complementary, so nothing is lost)


class PartsError(Exception):
    pass


# --- bands -----------------------------------------------------------------------------

def _validate(data, schema_name):
    try:
        import jsonschema
    except ImportError:
        return
    schema_path = SCHEMA_DIR / schema_name
    if schema_path.exists():
        try:
            jsonschema.validate(data, json.loads(schema_path.read_text()))
        except jsonschema.ValidationError as e:
            raise PartsError(f"{schema_name}: {e.message}") from e


def load_band(path):
    band = json.loads(Path(path).read_text())
    _validate(band, "banda.schema.json")
    ids = [m["id"] for m in band["musicians"]]
    if len(ids) != len(set(ids)):
        raise PartsError("Hay músicos con el mismo id en la banda.")
    return band


# --- sections --------------------------------------------------------------------------

def beats_per_bar(song):
    return int(song["tempo"]["timeSignature"].split("/")[0])


def section_bounds(song, n_frames, sr):
    """[(startBar, first_frame, end_frame)] covering the whole file.

    A section with `pickupBeats` (anacrusis) starts that many beats before its downbeat,
    so notes leading into it belong to whoever plays it.
    """
    g = grid.Grid(song["tempo"])
    starts = [s["startBar"] for s in song["sections"]]
    frames = [0] + [min(n_frames, max(0, round(g.bar_sec(s["startBar"], -s.get("pickupBeats", 0)) * sr)))
                    for s in song["sections"][1:]]
    return [(b, a, frames[i + 1] if i + 1 < len(frames) else n_frames) for i, (b, a) in enumerate(zip(starts, frames))]


def _labels(song):
    return {s["label"].lower(): s["label"] for s in song["stems"]}


# --- coverage --------------------------------------------------------------------------

def coverage(song, band, present=None):
    """What each present musician covers in this song.

    Returns ([{"id", "name", "stems": {label: set of startBars | None (whole song)}}], warnings).
    """
    labels = _labels(song)
    bars = {s["startBar"] for s in song["sections"]}
    present = None if present is None else {p.strip() for p in present if p.strip()}
    if present is not None:
        unknown = present - {m["id"] for m in band["musicians"]}
        if unknown:
            raise PartsError(f"No están en la banda: {', '.join(sorted(unknown))}")
    matrices = song.get("parts", {}).get(band["id"], {})
    result, warnings = [], []
    for m in band["musicians"]:
        if present is not None and m["id"] not in present:
            continue
        stems = {}
        if m["id"] in matrices:
            for bar, wanted in matrices[m["id"]].items():
                if int(bar) not in bars:
                    raise PartsError(f"{m['name']}: la matriz usa una sección que ya no existe (compás {bar}).")
                for w in wanted:
                    if w.lower() not in labels:
                        raise PartsError(f"{m['name']}: la canción no tiene el stem «{w}».")
                    stems.setdefault(labels[w.lower()], set()).add(int(bar))
        else:
            for w in m["default"]:
                if w.lower() in labels:
                    stems[labels[w.lower()]] = None
            if not stems:
                warnings.append(f"{m['name']}: la canción no tiene {', '.join(m['default'])}; no tendrá pista en vivo.")
        result.append({"id": m["id"], "name": m["name"], "stems": stems,
                       "sequence_level_db": m.get("sequenceLevelDb")})

    # one stem, one section, one musician: otherwise it would sound twice when unmuted
    claims = {}
    for r in result:
        for label, secs in r["stems"].items():
            for b in (bars if secs is None else secs):
                other = claims.setdefault((label, b), r["name"])
                if other != r["name"]:
                    raise PartsError(f"{label} en el compás {b} lo cubren {other} y {r['name']}.")
    return result, warnings


def mask(n_frames, bounds, covered, sr, ramp_s=RAMP_S):
    """1 inside the covered sections, 0 elsewhere, with short linear ramps at the edges."""
    step = np.zeros(n_frames, dtype=np.float32)
    for bar, a, b in bounds:
        if bar in covered:
            step[a:b] = 1.0
    w = max(1, int(ramp_s * sr))
    if w > 1:
        c = np.concatenate([[0.0], np.cumsum(np.pad(step, (w // 2, w - 1 - w // 2), mode="edge"), dtype=np.float64)])
        step = ((c[w:] - c[:-w]) / w).astype(np.float32)
    return step


# --- editing the matrix ----------------------------------------------------------------

SPEC = re.compile(r"^\s*([\d,\s-]+)\s*=\s*(.+)$")


def _section_numbers(text, n_sections):
    nums = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-"))
            nums.update(range(a, b + 1))
        elif part:
            nums.add(int(part))
    bad = [x for x in nums if not 1 <= x <= n_sections]
    if bad:
        raise PartsError(f"Secciones fuera de rango: {sorted(bad)} (la canción tiene {n_sections}).")
    return nums


def set_parts(song_dir, band, musician_id, specs=(), whole=None):
    song_path = Path(song_dir) / "cancion.json"
    song = json.loads(song_path.read_text())
    if musician_id not in {m["id"] for m in band["musicians"]}:
        raise PartsError(f"«{musician_id}» no está en la banda.")
    labels, sections = _labels(song), song["sections"]
    matrix = {}
    if whole:
        specs = [f"1-{len(sections)}={whole}"]
    for spec in specs:
        m = SPEC.match(spec)
        if not m:
            raise PartsError(f"No entiendo «{spec}». Formato: \"3=EG 1\" o \"4,5=EG 2+EG 3\".")
        stems = [w.strip() for w in m.group(2).split("+") if w.strip()]
        for w in stems:
            if w.lower() not in labels:
                raise PartsError(f"La canción no tiene el stem «{w}».")
        for num in _section_numbers(m.group(1), len(sections)):
            key = str(sections[num - 1]["startBar"])
            matrix[key] = sorted(set(matrix.get(key, [])) | {labels[w.lower()] for w in stems},
                                 key=lambda x: x.lower())
    song.setdefault("parts", {}).setdefault(band["id"], {})[musician_id] = dict(
        sorted(matrix.items(), key=lambda kv: int(kv[0])))
    # validate this musician's matrix; conflicts between musicians are checked at render
    # time, among those present that week (editing order must not matter)
    coverage(song, band, [musician_id])
    _validate(song, "cancion.schema.json")
    song_path.write_text(json.dumps(song, indent=1, ensure_ascii=False))
    return song


def set_matrix(song_dir, band, musician_id, matrix):
    """Replace a musician's whole matrix ({startBar: [labels]}); None or {} goes back to
    their default stems. What the app sends after every click."""
    if not matrix:
        clear_parts(song_dir, band, musician_id)
        return json.loads((Path(song_dir) / "cancion.json").read_text())
    song = json.loads((Path(song_dir) / "cancion.json").read_text())
    starts = [sec["startBar"] for sec in song["sections"]]
    specs = []
    for bar, labels in matrix.items():
        if int(bar) not in starts:
            raise PartsError(f"No hay una sección que empiece en el compás {bar}.")
        if labels:
            specs.append("%d=%s" % (starts.index(int(bar)) + 1, "+".join(labels)))
    if not specs:                      # nothing taken anywhere: an empty matrix, not the default
        song.setdefault("parts", {}).setdefault(band["id"], {})[musician_id] = {}
        (Path(song_dir) / "cancion.json").write_text(json.dumps(song, indent=1, ensure_ascii=False))
        return song
    return set_parts(song_dir, band, musician_id, specs)


def musician_stems(song, musician):
    """Stems a musician could play here: those of their role, plus their defaults."""
    want = {d.lower() for d in musician.get("default", [])}
    return [s["label"] for s in song["stems"]
            if s["role"] == musician.get("role") or s["label"].lower() in want]


def set_pickup(song_dir, section_number, beats):
    song_path = Path(song_dir) / "cancion.json"
    song = json.loads(song_path.read_text())
    if not 2 <= section_number <= len(song["sections"]):
        raise PartsError(f"La anacrusa va de la sección 2 a la {len(song['sections'])}.")
    if not 0 <= beats <= beats_per_bar(song):
        raise PartsError(f"Entre 0 y {beats_per_bar(song)} tiempos.")
    sec = song["sections"][section_number - 1]
    if beats:
        sec["pickupBeats"] = beats
    else:
        sec.pop("pickupBeats", None)
    _validate(song, "cancion.schema.json")
    song_path.write_text(json.dumps(song, indent=1, ensure_ascii=False))
    return song


def clear_parts(song_dir, band, musician_id):
    song_path = Path(song_dir) / "cancion.json"
    song = json.loads(song_path.read_text())
    band_parts = song.get("parts", {}).get(band["id"], {})
    band_parts.pop(musician_id, None)
    if not band_parts:
        song.get("parts", {}).pop(band["id"], None)
    if not song.get("parts"):
        song.pop("parts", None)
    song_path.write_text(json.dumps(song, indent=1, ensure_ascii=False))


# --- activity grid ---------------------------------------------------------------------

def activity(song_dir, song, roles=None, sr=22050):
    """Level (dBFS) of each stem in each section, to see who plays where."""
    if roles is None:
        counts = {}
        for s in song["stems"]:
            counts[s["role"]] = counts.get(s["role"], 0) + 1
        roles = {r for r, c in counts.items() if c > 1 and r not in ("click", "guide", "premix")}
    stems = [s for s in song["stems"] if s["role"] in roles]
    table = {}
    for s in stems:
        x = decode(Path(song_dir) / "originales" / s["file"], sr, mono=True)[:, 0] * printing.db_to_gain(s["gainDb"])
        levels = []
        for _, a, b in section_bounds(song, len(x), sr):
            seg = x[a:b]
            levels.append(float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)) if len(seg) else -120.0)
        table[s["label"]] = levels
    return table


def activity_cached(song_dir, song):
    """activity() for every stem but click and guide, kept in actividad.json next to the
    recipe until the stems or the sections change (decoding takes a few seconds)."""
    import hashlib
    key = hashlib.sha1(json.dumps([[s["label"], s["file"], s["gainDb"]] for s in song["stems"]] +
                                  [[x["startBar"], x.get("pickupBeats", 0)] for x in song["sections"]] +
                                  [song["tempo"]], sort_keys=True).encode()).hexdigest()
    cache = Path(song_dir) / "actividad.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            if data.get("key") == key:
                return data["levels"]
        except ValueError:
            pass
    roles = {s["role"] for s in song["stems"]} - {"click", "guide"}
    levels = activity(song_dir, song, roles)
    cache.write_text(json.dumps({"key": key, "levels": levels}))
    return levels


def _cell(level, loudest):
    if level < -60 or level < loudest - 30:
        return "  ·  "
    return " ███ " if level >= loudest - 12 else " ░░░ "


def print_grid(song, table):
    labels = list(table)
    print(f"{'#':>3}  {'Sección':12} {'Compases':9}" + "".join(f"{l[:5]:^5}" for l in labels))
    loudest = {l: max(v) for l, v in table.items()}
    for i, sec in enumerate(song["sections"]):
        bars = f"{sec['startBar']}–{sec['startBar'] + sec['bars'] - 1}"
        print(f"{i + 1:>3}  {sec['name'][:12]:12} {bars:9}" + "".join(_cell(table[l][i], loudest[l]) for l in labels))
    print("     ███ fuerte   ░░░ suave   · no suena")


def print_coverage(song, band, present=None):
    cov, warnings = coverage(song, band, present)
    for r in cov:
        if not r["stems"]:
            continue
        print(f"{r['name']}:")
        for i, sec in enumerate(song["sections"]):
            plays = [l for l, secs in r["stems"].items() if secs is None or sec["startBar"] in secs]
            print(f"  {i + 1:>2} {sec['name'][:12]:12} {', '.join(plays) if plays else '— (no toca)'}")
    for w in warnings:
        print(f"⚠ {w}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid"); g.add_argument("song"); g.add_argument("--role", action="append")
    sh = sub.add_parser("show"); sh.add_argument("song"); sh.add_argument("--band", required=True)
    sh.add_argument("--presentes")
    st = sub.add_parser("set"); st.add_argument("song"); st.add_argument("--band", required=True)
    st.add_argument("--musician", required=True)
    st.add_argument("--secciones", dest="specs", nargs="+", default=[], metavar="SECCIONES=STEMS")
    st.add_argument("--whole")
    pk = sub.add_parser("pickup", help="Anacrusa: adelantar el inicio de una sección N tiempos")
    pk.add_argument("song"); pk.add_argument("section", type=int); pk.add_argument("beats", type=float)
    cl = sub.add_parser("clear"); cl.add_argument("song"); cl.add_argument("--band", required=True)
    cl.add_argument("--musician", required=True)
    args = ap.parse_args(argv)
    try:
        song = json.loads((Path(args.song) / "cancion.json").read_text())
        if args.cmd == "grid":
            print_grid(song, activity(args.song, song, set(args.role) if args.role else None))
        elif args.cmd == "show":
            print_coverage(song, load_band(args.band), args.presentes.split(",") if args.presentes else None)
        elif args.cmd == "set":
            band = load_band(args.band)
            if not args.specs and not args.whole:
                raise PartsError("Indica las secciones (\"3=EG 1\") o --whole \"EG 1\".")
            song = set_parts(args.song, band, args.musician, args.specs, args.whole)
            print_coverage(song, band, [args.musician])
        elif args.cmd == "pickup":
            set_pickup(args.song, args.section, args.beats)
            print(f"Sección {args.section}: empieza {args.beats:g} tiempo(s) antes.")
        elif args.cmd == "clear":
            clear_parts(args.song, load_band(args.band), args.musician)
            print("Matriz borrada: se usarán sus stems por defecto.")
    except PartsError as e:
        print(f"No se pudo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
