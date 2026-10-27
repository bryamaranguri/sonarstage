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


def test_bar_one_lands_on_a_bar_line_when_the_audio_starts_before_it():
    a = song("A", 120, 10.0)
    a["tempo"]["firstDownbeatSec"] = 0.75                 # click starts 1.5 beats before bar 1
    b = song("B", 120, 10.0)
    downs = ableton.plan_layout([a, b], gap_seconds=1)
    assert downs[0] == 4                                   # files start at beat 2.5, bar 1 on beat 4
    assert ableton._song_start(a, downs[0]) == pytest.approx(2.5)
    assert downs[1] == 28                                  # A ends at 22.5, +2 beats of gap = 24.5, next bar


def test_layout_follows_the_tempo_map():
    s = song("Rit", 120, 20.0)
    s["tempo"]["map"] = [{"beat": 0, "sec": 0.0, "bpm": 120}, {"beat": 16, "sec": 8.0, "bpm": 60}]
    nxt = song("B", 90, 5.0)
    downs = ableton.plan_layout([s, nxt], gap_seconds=4)
    # 16 beats in 8 s, then 12 s at 60 = 12 beats -> ends at 28; 4 s at 60 = 4 beats -> 32
    assert downs == [0, 32]


@pytest.mark.skipif(not TEMPLATE, reason="definir SONARSTAGE_TEMPLATE con una plantilla .als real")
def test_tempo_automation_follows_the_map(tmp_path):
    path = tmp_path / "Click.wav"
    sf.write(path, np.zeros((20 * 48000, 2), np.float32), 48000)
    s = song("Rit", 120, 20.0, sections=((1, "Inicio"), (5, "Final")))
    s["tempo"]["map"] = [{"beat": 0, "sec": 0.0, "bpm": 120}, {"beat": 16, "sec": 8.0, "bpm": 60}]
    s["files"] = [{"group": "CUES", "label": "Click", "path": str(path), "frames": 20 * 48000, "sr": 48000}]
    nxt = song("Dos", 90, 1.0)
    nxt["files"] = [dict(s["files"][0], frames=48000)]
    ableton.build_set(TEMPLATE, [s, nxt], tmp_path / "Show.als", gap_seconds=4)
    ls = ET.fromstring(gzip.open(tmp_path / "Show.als").read()).find("LiveSet")
    tempo = [(float(e.get("Time")), float(e.get("Value"))) for e in ls.find("MainTrack").iter("FloatEvent")]
    assert tempo[1:] == [(16.0, 120.0), (16.0, 60.0), (32.0, 60.0), (32.0, 90.0)]
    clip = next(c for c in ls.iter("AudioClip") if c.find("Name").get("Value").startswith("Rit"))
    assert float(clip.find("CurrentEnd").get("Value")) == pytest.approx(28.0)
    locs = {l.find("Name").get("Value"): float(l.find("Time").get("Value")) for l in ls.iter("Locator")}
    assert locs["Final"] == 16.0 and locs["2. Dos"] == 32.0


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


@pytest.mark.skipif(not TEMPLATE, reason="definir SONARSTAGE_TEMPLATE con una plantilla .als real")
def test_talkback_track_listens_to_the_mic_and_goes_out_with_the_click(tmp_path):
    path = tmp_path / "Click.wav"
    sf.write(path, np.zeros((48000, 2), np.float32), 48000)
    s = song("Uno", 72, 1.0)
    s["files"] = [{"group": "CUES", "label": "Click", "path": str(path), "frames": 48000, "sr": 48000}]
    als = tmp_path / "Show.als"
    result = ableton.build_set(TEMPLATE, [s], als, profile="2", gap_seconds=2, talkback=2)
    ls = ET.fromstring(gzip.open(als).read()).find("LiveSet")
    tracks = {t.find("Name/EffectiveName").get("Value"): t for t in ls.find("Tracks")}
    assert list(tracks) == ["CUES", "Click", "TALKBACK"]
    tb = tracks["TALKBACK"]
    assert tb.find("TrackGroupId").get("Value") == tracks["CUES"].get("Id")
    assert tb.find("DeviceChain/AudioInputRouting/Target").get("Value") == "AudioIn/External/M1"
    assert tb.find("DeviceChain/AudioInputRouting/LowerDisplayString").get("Value") == "2"
    assert tb.find("DeviceChain/MainSequencer/MonitoringEnum").get("Value") == "0"
    assert tb.find("DeviceChain/Mixer/Speaker/Manual").get("Value") == "true"
    assert not list(tb.iter("AudioClip"))
    assert tracks["CUES"].find("DeviceChain/AudioOutputRouting/LowerDisplayString").get("Value") == "2"
    assert ("CUES", "TALKBACK") in result["tracks"]
    with pytest.raises(ableton.AlsError):
        ableton.build_set(TEMPLATE, [s], tmp_path / "Otro.als", talkback=0)


@pytest.mark.skipif(not TEMPLATE, reason="definir SONARSTAGE_TEMPLATE con una plantilla .als real")
def test_no_talkback_by_default(tmp_path):
    path = tmp_path / "Click.wav"
    sf.write(path, np.zeros((48000, 2), np.float32), 48000)
    s = song("Uno", 72, 1.0)
    s["files"] = [{"group": "CUES", "label": "Click", "path": str(path), "frames": 48000, "sr": 48000}]
    ableton.build_set(TEMPLATE, [s], tmp_path / "Show.als")
    ls = ET.fromstring(gzip.open(tmp_path / "Show.als").read()).find("LiveSet")
    assert "TALKBACK" not in [t.find("Name/EffectiveName").get("Value") for t in ls.find("Tracks")]


CLICK_TEMPLATE = os.environ.get("SONARSTAGE_CLICK_TEMPLATE")


@pytest.mark.skipif(not (TEMPLATE and CLICK_TEMPLATE),
                    reason="definir SONARSTAGE_TEMPLATE y SONARSTAGE_CLICK_TEMPLATE")
def test_midi_click_plays_the_click_beats_with_accents(tmp_path):
    path = tmp_path / "Click.wav"
    sf.write(path, np.zeros((48000 * 4, 2), np.float32), 48000)
    s = song("Uno", 120, 4.0)
    s["files"] = [{"group": "CUES", "label": "Click", "path": str(path), "frames": 48000 * 4, "sr": 48000}]
    s["click_beats"] = [-1, 0, 1, 2, 3, 4, 5, 7]          # a pickup and a silent beat (6)
    result = ableton.build_set(TEMPLATE, [s], tmp_path / "Show.als", click_template=CLICK_TEMPLATE)
    ls = ET.fromstring(gzip.open(tmp_path / "Show.als").read()).find("LiveSet")
    tracks = {t.find("Name/EffectiveName").get("Value"): t for t in ls.find("Tracks")}
    assert list(tracks) == ["CUES", "Click", "Click original"]
    assert tracks["Click original"].find("DeviceChain/Mixer/Speaker/Manual").get("Value") == "false"
    clips = list(tracks["Click"].iter("MidiClip"))
    assert len(clips) == 1
    clip = clips[0]
    assert float(clip.get("Time")) == -1.0 + result["starts"][0]
    notes = {kt.find("MidiKey").get("Value"): [float(n.get("Time")) for n in kt.iter("MidiNoteEvent")]
             for kt in clip.iter("KeyTrack")}
    assert notes["36"] == [1.0, 5.0] and notes["37"] == [0.0, 2.0, 3.0, 4.0, 6.0, 8.0]
    samples = [p.get("Value") for p in tracks["Click"].iter("RelativePath") if p.get("Value", "").endswith(".wav")]
    assert sorted(samples) == ["Audio/Click/click-accent.wav", "Audio/Click/click-beat.wav"]
    assert (tmp_path / "Audio" / "Click" / "click-accent.wav").exists()
    pids = [int(e.get("Id")) for e in ls.iter() if "Id" in e.attrib and (
        e.tag == "Pointee" or e.tag.endswith("Target") or e.tag.startswith("ControllerTargets."))]
    assert not [k for k, v in Counter(pids).items() if v > 1]
    assert result["midi_click"]
