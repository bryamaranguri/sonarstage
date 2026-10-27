"""Library song folders and cancion.json (see shared/cancion.schema.json)."""
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import grid

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "shared" / "cancion.schema.json"


def slugify(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "cancion"


def title_from_source(name):
    """'MT HOLY FOREVER BETHEL MUSIC.rar' -> 'Holy Forever Bethel Music' (the user edits it)."""
    stem = Path(name).stem if Path(name).suffix else name
    stem = re.sub(r"^\s*(mt|multitracks?)\s+", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem.replace("_", " ")).strip()
    return stem.title() if stem.isupper() else stem


def sections_from_cues(cues, total_bars, min_gap_bars=2, lead_bars=1):
    """Provisional sections from where the guide speaks on beat 1.

    The guide announces a section during the bar before it ("Coro…" and the section
    starts on the next downbeat), so each cue opens a section `lead_bars` later. Measured
    on two real packs: the mix energy changes most one bar after the cue. Cues in
    consecutive bars are one announcement and the section starts after the last one; the
    count-in (bars 1 and 2) becomes its own first section. Boundaries closer than
    `min_gap_bars` merge. Names stay generic until the guide is transcribed.
    """
    downbeats = sorted({c["bar"] for c in cues if c["beat"] < 1.5})
    count_in = 1 in downbeats
    # An announcement can span consecutive bars ("Coro…" then "dos, tres"): the section
    # starts after its last bar.
    announcements = []
    for bar in downbeats:
        if announcements and bar - announcements[-1][-1] == 1:
            announcements[-1].append(bar)
        else:
            announcements.append([bar])
    starts = [1]
    for group in announcements:
        start = group[-1] + lead_bars
        if start - starts[-1] >= min_gap_bars:
            starts.append(start)
    starts = [b for b in starts if b <= total_bars]
    sections = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total_bars + 1
        if end > start:
            name = ("Cuenta" if count_in else "Inicio") if i == 0 else f"Sección {i}"
            sections.append({"name": name, "kind": "other", "startBar": int(start), "bars": int(end - start)})
    return sections


def total_bars(duration_s, tempo):
    g = grid.Grid(tempo)
    return max(1, math.ceil(g.beat(duration_s) / g.bpb - 1e-9))


def song_tempo(report, duration_s=None):
    """cancion.json tempo from the analysis: the map, plus the main tempo and bar 1."""
    t = report["tempo"]
    meter = report.get("meter", {})
    bpb = meter.get("beats_per_bar", 4)
    phase = meter.get("downbeat_phase", 0)
    tmap = t.get("map") or []
    if not tmap:
        return {"bpm": t["bpm"], "timeSignature": f"{bpb}/4", "map": [],
                "firstDownbeatSec": round(t["first_beat_s"] + phase * 60 / t["bpm"], 4)}
    g = grid.Grid({"bpm": tmap[0]["bpm"], "timeSignature": f"{bpb}/4", "map": tmap})
    end = g.beat(duration_s) if duration_s else None
    return {"bpm": grid.main_bpm(tmap, end), "timeSignature": f"{bpb}/4", "map": tmap,
            "firstDownbeatSec": round(max(0.0, g.sec(0)), 4)}


def build_song_json(*, song_id, title, source, report, stems, sections, target_lufs, prepared_semitones=(0,),
                    duration_s=None, key_estimate=None):
    key = {"original": "?", "prepared": list(prepared_semitones)}
    if key_estimate:
        key.update(estimated=key_estimate["key"], confidence=key_estimate["confidence"], confirmed=False)
    return {
        "schemaVersion": 1,
        "id": song_id,
        "title": title,
        "source": source,
        "importedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tempo": song_tempo(report, duration_s),
        "key": key,
        "sections": sections,
        "stems": stems,
        "mix": {"targetLufs": target_lufs, "songOffsetDb": 0},
        "notes": "Secciones provisionales desde la guía; tonalidad estimada, por confirmar.",
    }


def validate(song):
    """Validate against the shared schema when jsonschema is installed. Returns error or None."""
    try:
        import jsonschema
    except ImportError:
        return None
    if not SCHEMA_PATH.exists():
        return None
    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(song, schema)
    except jsonschema.ValidationError as e:
        return e.message
    return None
