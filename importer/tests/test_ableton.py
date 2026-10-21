"""Show layout and, when a real template is available, the generated Live set."""
import gzip
import os
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from sonarstage_import import ableton

TEMPLATE = os.environ.get("SONARSTAGE_TEMPLATE")


def song(title, bpm, seconds, sections=((1, "Inicio"), (3, "Verso"))):
    return {"title": title, "tempo": {"bpm": bpm, "timeSignature": "4/4", "firstDownbeatSec": 0.0},
            "sections": [{"name": n, "startBar": b, "bars": 2} for b, n in sections],
            "duration_s": seconds, "files": []}


def test_layout_gaps_start_on_a_bar():
    starts = ableton.plan_layout([song("A", 72, 323.333), song("B", 128, 283.1), song("C", 90, 60)], gap_seconds=30)
    assert starts[0] == 0
    assert starts[1] == 424                  # 388 beats of song A, then 36 beats (30 s at 72), on a bar
    assert all(s % 4 == 0 for s in starts)
    assert starts[2] > starts[1] + 283.1 * 128 / 60


@pytest.mark.skipif(not TEMPLATE, reason="definir SONARSTAGE_TEMPLATE con una plantilla .als real")
def test_generated_set_is_consistent(tmp_path):
    songs = []
    for title, bpm, secs in (("Uno", 72, 8.0), ("Dos", 128, 6.0)):
        files = []
        for group, label in (("CUES", "Click"), ("EN VIVO", "Guitarra"), ("SECUENCIA", "Secuencia")):
            path = tmp_path / title / f"{label}.wav"
            path.parent.mkdir(exist_ok=True)
            sf.write(path, np.zeros((int(secs * 48000), 2), np.float32), 48000)
            files.append({"group": group, "label": label, "path": str(path), "frames": int(secs * 48000), "sr": 48000})
        s = song(title, bpm, secs)
        s["files"] = files
        songs.append(s)
    als = tmp_path / "Show.als"
    ableton.build_set(TEMPLATE, songs, als, profile="2", gap_seconds=2)
    ls = ET.fromstring(gzip.open(als).read()).find("LiveSet")
    pids = [int(e.get("Id")) for e in ls.iter() if "Id" in e.attrib and (e.tag == "Pointee" or e.tag.endswith("Target"))]
    assert not [k for k, v in Counter(pids).items() if v > 1]
    assert max(pids) < int(ls.find("NextPointeeId").get("Value"))
    names = [t.find("Name/EffectiveName").get("Value") for t in ls.find("Tracks")]
    assert names == ["CUES", "Click", "EN VIVO", "Guitarra", "SECUENCIA", "Secuencia"]
    muted = {t.find("Name/EffectiveName").get("Value"): t.find("DeviceChain/Mixer/Speaker/Manual").get("Value") == "false"
             for t in ls.find("Tracks")}
    assert muted["Guitarra"] and not muted["Secuencia"]
    assert ls.find("MainTrack/DeviceChain/AudioOutputRouting/LowerDisplayString").get("Value") == "1"
    tempo = [(e.get("Time"), float(e.get("Value"))) for e in ls.find("MainTrack").iter("FloatEvent")]
    assert tempo[0][1] == 72 and tempo[-1][1] == 128 and tempo[-1][0] == tempo[-2][0]
    clips = list(ls.iter("AudioClip"))
    assert len(clips) == 6 and all(c.find("IsWarped").get("Value") == "false" for c in clips)
    first = [c for c in clips if c.find("Name").get("Value").startswith("Uno")][0]
    assert float(first.find("CurrentEnd").get("Value")) == pytest.approx(8.0 * 72 / 60)
    locators = [l.find("Name").get("Value") for l in ls.iter("Locator")]
    assert locators == ["1. Uno", "Verso", "2. Dos", "Verso"]
