"""MIDI changes per section, and the MIDI lanes of a show.

    python -m sonarstage_import.midi set <song> --band <banda.json> --device hx-stomp --seccion 3 [--preset 4] [--snapshot 2] [--cc 20=127]
    python -m sonarstage_import.midi clear <song> --band <banda.json> --device hx-stomp --seccion 3
    python -m sonarstage_import.midi show <song> --band <banda.json>

Devices are declared in the band (`midiDevices`). Kinds:
- hx-stomp: preset = Program Change, snapshot = CC 69 (0, 1, 2 = snapshots 1-3), and any
  CC assigned to a block's bypass (0-63 off, 64-127 on). The pedal also follows Live's
  MIDI Clock, which comes from the tempo automation, so no tempo lane is needed.
- tap-tempo: the UAD Console only takes tempo as taps (a note or CC). The show taps
  that CC on every beat of the count-in, so the console has the song's tempo when the
  music starts.
- generic: Program Change and CC as given.
Section numbers are those of `parts grid`; changes are stored by the section's first bar.
"""
import argparse
import json
import sys
from pathlib import Path

from . import parts

HX_SNAPSHOT_CC = 69
TAP_LENGTH = 0.125        # beats each tap stays high


class MidiError(Exception):
    pass


def _device(band, device_id):
    for d in band.get("midiDevices", []):
        if d["id"] == device_id:
            return d
    raise MidiError(f"«{device_id}» no está entre los dispositivos MIDI de la banda.")


def set_change(song_dir, band, device_id, section_number, preset=None, snapshot=None, cc=None, clear=False):
    device = _device(band, device_id)
    if device["kind"] == "tap-tempo":
        raise MidiError("El tap tempo se genera solo con el tempo de cada canción; no se edita por sección.")
    path = Path(song_dir) / "cancion.json"
    song = json.loads(path.read_text())
    if not 1 <= section_number <= len(song["sections"]):
        raise MidiError(f"La canción tiene {len(song['sections'])} secciones.")
    if snapshot is not None and device["kind"] == "hx-stomp" and not 1 <= snapshot <= 3:
        raise MidiError("La HX Stomp tiene 3 snapshots.")
    key = str(song["sections"][section_number - 1]["startBar"])
    dev = song.setdefault("midi", {}).setdefault(band["id"], {}).setdefault(device_id, {})
    if clear:
        dev.pop(key, None)
    else:
        change = dev.setdefault(key, {})
        if preset is not None:
            change["preset"] = preset
        if snapshot is not None:
            change["snapshot"] = snapshot
        if cc:
            change.setdefault("cc", {}).update({str(k): v for k, v in cc.items()})
        if not change:
            dev.pop(key)
            raise MidiError("Indica --preset, --snapshot o --cc.")
    song["midi"][band["id"]][device_id] = dict(sorted(dev.items(), key=lambda kv: int(kv[0])))
    parts._validate(song, "cancion.schema.json")
    path.write_text(json.dumps(song, indent=1, ensure_ascii=False))
    return song


def _section_beat(song, start_bar):
    t = song["tempo"]
    bpb = int(t["timeSignature"].split("/")[0])
    offset = t.get("firstDownbeatSec", 0)
    first = offset * t["bpm"] / 60 if offset > 0.02 else 0.0
    return first + (start_bar - 1) * bpb


def lanes(song, band, song_beats):
    """MIDI lanes of one song for the show generator (times in beats from the song start)."""
    result = []
    for device in band.get("midiDevices", []):
        events = []
        if device["kind"] == "tap-tempo":
            if "tapCc" not in device:
                raise MidiError(f"{device['name']}: falta tapCc (el CC asignado al tap tempo en la consola).")
            first = song["sections"][0]
            bpb = int(song["tempo"]["timeSignature"].split("/")[0])
            taps = first["bars"] * bpb if first["name"] == "Cuenta" else bpb
            points = [(0, 0)]
            for b in range(taps):
                points += [(b, 127), (b + TAP_LENGTH, 127), (b + TAP_LENGTH, 0)]
            events.append({"time": 0.0, "length": float(taps), "name": f"Tap {song['tempo']['bpm']:g}",
                           "envelopes": {device["tapCc"]: points}})
        else:
            changes = song.get("midi", {}).get(band["id"], {}).get(device["id"], {})
            bars = sorted(int(b) for b in changes)
            for i, bar in enumerate(bars):
                ch = changes[str(bar)]
                start = _section_beat(song, bar)
                end = _section_beat(song, bars[i + 1]) if i + 1 < len(bars) else song_beats
                env = {int(k): [(0, v)] for k, v in ch.get("cc", {}).items()}
                if "snapshot" in ch:
                    env[HX_SNAPSHOT_CC] = [(0, ch["snapshot"] - 1)]     # Helix family: CC 69, 0 = snapshot 1
                name = " · ".join(x for x in (f"Preset {ch['preset']}" if "preset" in ch else "",
                                              f"Snap {ch['snapshot']}" if "snapshot" in ch else "",
                                              " ".join(f"CC{k}={v}" for k, v in ch.get("cc", {}).items())) if x)
                events.append({"time": start, "length": max(end - start, 1.0), "name": name,
                               "program": ch.get("preset"), "envelopes": env})
        if events:
            result.append({"label": device["name"], "events": events})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("set", "clear", "show"):
        sp = sub.add_parser(name)
        sp.add_argument("song")
        sp.add_argument("--band", required=True)
        if name != "show":
            sp.add_argument("--device", required=True)
            sp.add_argument("--seccion", type=int, required=True)
        if name == "set":
            sp.add_argument("--preset", type=int)
            sp.add_argument("--snapshot", type=int)
            sp.add_argument("--cc", nargs="+", default=[], metavar="CC=VALOR")
    args = ap.parse_args(argv)
    try:
        band = parts.load_band(args.band)
        if args.cmd == "show":
            song = json.loads((Path(args.song) / "cancion.json").read_text())
        else:
            cc = {}
            for item in getattr(args, "cc", []):
                k, _, v = item.partition("=")
                cc[int(k)] = int(v)
            song = set_change(args.song, band, args.device, args.seccion, getattr(args, "preset", None),
                              getattr(args, "snapshot", None), cc, clear=args.cmd == "clear")
        starts = {s["startBar"]: (i + 1, s["name"]) for i, s in enumerate(song["sections"])}
        for dev_id, changes in song.get("midi", {}).get(band["id"], {}).items():
            print(f"{_device(band, dev_id)['name']}:")
            for bar, ch in changes.items():
                n, name = starts[int(bar)]
                print(f"  {n:>2} {name:12} {json.dumps(ch, ensure_ascii=False)}")
    except (MidiError, parts.PartsError) as e:
        print(f"No se pudo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
