"""Library song folders and cancion.json (see shared/cancion.schema.json)."""
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

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


def sections_from_cues(cues, total_bars, min_gap_bars=2):
    """Provisional sections from where the guide speaks on beat 1.

    Cues one bar apart are one announcement ("coro… dos, tres, cuatro"), so they merge.
    The first section always starts at bar 1 (it contains the count-in). Names stay
    generic until the guide is transcribed.
    """
    downbeats = sorted({c["bar"] for c in cues if c["beat"] < 1.5})
    starts = []
    for bar in downbeats:
        if not starts or bar - starts[-1] >= min_gap_bars:
            starts.append(bar)
    if not starts or starts[0] != 1:
        starts.insert(0, 1)
    starts = [b for b in starts if b <= total_bars]
    sections = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total_bars + 1
        if end > start:
            sections.append({"name": "Inicio" if i == 0 else f"Sección {i}", "kind": "other",
                             "startBar": int(start), "bars": int(end - start)})
    return sections


def total_bars(duration_s, bpm, first_downbeat_s, beats_per_bar):
    bar_s = 60 / bpm * beats_per_bar
    return max(1, math.ceil((duration_s - first_downbeat_s) / bar_s))


def build_song_json(*, song_id, title, source, report, stems, sections, target_lufs, prepared_semitones=(0,)):
    t = report["tempo"]
    meter = report.get("meter", {})
    bpb = meter.get("beats_per_bar", 4)
    phase = meter.get("downbeat_phase", 0)
    return {
        "schemaVersion": 1,
        "id": song_id,
        "title": title,
        "source": source,
        "importedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tempo": {
            "bpm": t["bpm"],
            "timeSignature": f"{bpb}/4",
            "map": [],   # tempo changes: pending (both tested packs are constant)
            "firstDownbeatSec": round(t["first_beat_s"] + phase * 60 / t["bpm"], 4),
        },
        "key": {"original": "?", "prepared": list(prepared_semitones)},
        "sections": sections,
        "stems": stems,
        "mix": {"targetLufs": target_lufs, "songOffsetDb": 0},
        "notes": "Secciones provisionales desde la guía; tonalidad pendiente.",
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
