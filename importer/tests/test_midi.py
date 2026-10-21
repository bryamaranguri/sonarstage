"""MIDI changes per section and the lanes they become in a show."""
import gzip
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from sonarstage_import import ableton, midi

from test_parts import band, song_dir  # noqa: F401  (fixtures)

TEMPLATE = os.environ.get("SONARSTAGE_TEMPLATE")


@pytest.fixture
def midi_band(band):  # noqa: F811
    band["midiDevices"] = [{"id": "hx-stomp", "name": "HX Stomp", "kind": "hx-stomp", "channel": 1},
                           {"id": "consola", "name": "Consola UAD", "kind": "tap-tempo", "channel": 1, "tapCc": 20}]
    return band


def test_set_and_lanes(song_dir, midi_band):  # noqa: F811
    midi.set_change(song_dir, midi_band, "hx-stomp", 2, preset=4, snapshot=1)
    midi.set_change(song_dir, midi_band, "hx-stomp", 3, snapshot=3, cc={20: 127})
    song = json.loads((song_dir / "cancion.json").read_text())
    assert song["midi"]["mi-banda"]["hx-stomp"] == {"3": {"preset": 4, "snapshot": 1}, "7": {"snapshot": 3, "cc": {"20": 127}}}
    lanes = {l["label"]: l["events"] for l in midi.lanes(song, midi_band, song_beats=40)}
    hx = lanes["HX Stomp"]
    assert [(e["time"], e["length"], e.get("program")) for e in hx] == [(8.0, 16.0, 4), (24.0, 16.0, None)]
    assert hx[0]["envelopes"] == {69: [(0, 0)]} and hx[1]["envelopes"] == {20: [(0, 127)], 69: [(0, 2)]}
    tap = lanes["Consola UAD"][0]
    highs = [t for t, v in tap["envelopes"][20] if v == 127]
    assert tap["length"] == 8 and sorted(set(highs))[:3] == [0, 0.125, 1]   # one tap per beat of the 2-bar count-in


def test_bad_requests(song_dir, midi_band):  # noqa: F811
    with pytest.raises(midi.MidiError):
        midi.set_change(song_dir, midi_band, "hx-stomp", 2, snapshot=4)     # HX Stomp has 3
    with pytest.raises(midi.MidiError):
        midi.set_change(song_dir, midi_band, "consola", 2, preset=1)        # tap tempo is automatic
    with pytest.raises(midi.MidiError):
        midi.set_change(song_dir, midi_band, "nada", 2, preset=1)
    with pytest.raises(midi.MidiError):
        midi.set_change(song_dir, midi_band, "hx-stomp", 9, preset=1)


@pytest.mark.skipif(not TEMPLATE, reason="definir SONARSTAGE_TEMPLATE con una plantilla .als real")
def test_midi_tracks_in_the_set(tmp_path):
    tpl = ableton.Template(TEMPLATE)
    if tpl.midi_proto is None:
        pytest.skip("la plantilla no tiene pista MIDI")
    path = tmp_path / "Click.wav"
    sf.write(path, np.zeros((48000 * 8, 2), np.float32), 48000)
    song = {"title": "Uno", "tempo": {"bpm": 120, "timeSignature": "4/4", "firstDownbeatSec": 0.0},
            "sections": [{"name": "Cuenta", "startBar": 1, "bars": 2}, {"name": "Verso", "startBar": 3, "bars": 2}],
            "duration_s": 8.0,
            "files": [{"group": "CUES", "label": "Click", "path": str(path), "frames": 48000 * 8, "sr": 48000}],
            "midi": [{"label": "HX Stomp", "events": [
                {"time": 8.0, "length": 8.0, "name": "Preset 4 · Snap 2", "program": 4, "envelopes": {69: [(0, 1)]}}]}]}
    als = tmp_path / "Show.als"
    ableton.build_set(TEMPLATE, [song], als)
    ls = ET.fromstring(gzip.open(als).read()).find("LiveSet")
    pids = [int(e.get("Id")) for e in ls.iter() if "Id" in e.attrib and (
        e.tag == "Pointee" or e.tag.endswith("Target") or e.tag.startswith("ControllerTargets."))]
    assert not [k for k, v in Counter(pids).items() if v > 1]
    assert max(pids) < int(ls.find("NextPointeeId").get("Value"))
    track = [t for t in ls.find("Tracks") if t.tag == "MidiTrack"]
    assert [t.find("Name/EffectiveName").get("Value") for t in track] == ["HX Stomp"]
    clip = track[0].find("DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events/MidiClip")
    assert clip.find("ProgramChange").get("Value") == "4" and clip.get("Time") == "8.0"
    pointee = clip.find("Envelopes/Envelopes/ClipEnvelope/EnvelopeTarget/PointeeId").get("Value")
    assert pointee == track[0].find("DeviceChain/MainSequencer/MidiControllers/ControllerTargets.71").get("Id")
