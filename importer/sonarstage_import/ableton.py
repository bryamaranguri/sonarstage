"""Write an Ableton Live set (.als) for a show.

Template-based on purpose: every track, clip and envelope is cloned from a set that
Live itself saved (the user's template), and only names, colors, routing, positions
and file references are changed. The .als format is not documented, so writing
elements from scratch would be guessing; cloning keeps the structure Live expects.
The result declares the template's Live version, so it opens in that version or later.

Layout of the set (docs/plantilla.md):
  CUES       (gray)    → click and guide, to the cue output
  EN VIVO    (purple)  → one track per musician, muted, to Main
  SECUENCIA  (yellow)  → the summed sequence, to Main
  CONTROL              → one MIDI track per device (pedalboard presets/snapshots,
                         tap tempo for the Apollo console); only when the template has
                         a MIDI track with a clip to clone
Songs go one after another in the arrangement with a gap; the tempo follows each song
through tempo automation; clips are unwarped (audio plays untouched, nothing is
time-stretched on stage). Locators mark each song and its sections.
"""
import copy
import gzip
import math
import os
import xml.etree.ElementTree as ET

COLORS = {  # Live color indexes taken from the user's template
    "CUES": (41, 13), "EN VIVO": (64, 24), "SECUENCIA": (1, 3), "CONTROL": (14, 14),
}
CC_TARGET_OFFSET = 2   # a MIDI track's ControllerTargets.N controls CC N-2 (CC 69 = .71 in Live 12)

# Output profiles: (Target, UpperDisplayString, LowerDisplayString)
PROFILES = {
    # 2-output interface: sequence summed to mono on output 1, click + guide on output 2.
    # Needs outputs 1 and 2 enabled as mono in Live (Preferences > Audio > Output Config).
    "2": {"main": ("AudioOut/External/M0", "Ext. Out", "1"), "cues": ("AudioOut/External/M1", "Ext. Out", "2")},
    # stereo sequence on 1/2, cues on 3/4 (4+ output interfaces)
    "4": {"main": ("AudioOut/External/S0", "Ext. Out", "1/2"), "cues": ("AudioOut/External/S1", "Ext. Out", "3/4")},
}
TO_GROUP = ("AudioOut/GroupTrack", "Group", "")
TO_MAIN = ("AudioOut/Main", "Main", "")
FOREVER_AGO = "-63072000"           # time Live uses for an envelope's initial value


class AlsError(Exception):
    pass


class _Ids:
    """Hands out pointee ids (automation/modulation targets) above everything in the set."""

    def __init__(self, start):
        self.next = start

    def renumber(self, elem):
        for e in elem.iter():
            if "Id" in e.attrib and (e.tag == "Pointee" or e.tag.endswith("Target")
                                     or e.tag.startswith("ControllerTargets.")):
                e.set("Id", str(self.next))
                self.next += 1


def _set(elem, path, value):
    node = elem.find(path)
    if node is None:
        raise AlsError(f"La plantilla no tiene {path}")
    node.set("Value", str(value))


def _route(track, routing):
    r = track.find("DeviceChain/AudioOutputRouting")
    for tag, value in zip(("Target", "UpperDisplayString", "LowerDisplayString"), routing):
        r.find(tag).set("Value", value)


class Template:
    def __init__(self, path):
        with gzip.open(path) as f:
            self.root = ET.fromstring(f.read())
        self.liveset = self.root.find("LiveSet")
        tracks = list(self.liveset.find("Tracks"))
        self.group_proto = next((t for t in tracks if t.tag == "GroupTrack"), None)
        self.audio_proto = next((t for t in tracks if t.tag == "AudioTrack" and t.find(".//AudioClip") is not None), None)
        if self.group_proto is None or self.audio_proto is None:
            raise AlsError("La plantilla necesita al menos un grupo y una pista de audio con un clip.")
        self.clip_proto = self.audio_proto.find(".//AudioClip")
        self.midi_proto = next((t for t in tracks if t.tag == "MidiTrack" and t.find(".//MidiClip") is not None), None)
        self.midi_clip_proto = self.midi_proto.find(".//MidiClip") if self.midi_proto is not None else None
        env = self.midi_clip_proto.find("Envelopes/Envelopes/ClipEnvelope") if self.midi_proto is not None else None
        self.envelope_proto = env
        self.version = self.root.get("Creator")


def _clip(proto, ids, clip_id, *, start, bpm, seconds, name, color, path, rel_path, frames, sr, size, mtime):
    c = copy.deepcopy(proto)
    length = seconds * bpm / 60.0
    c.set("Id", str(clip_id))
    c.set("Time", repr(start))
    _set(c, "CurrentStart", repr(start))
    _set(c, "CurrentEnd", repr(start + length))
    for tag, value in (("LoopStart", 0), ("LoopEnd", length), ("StartRelative", 0), ("LoopOn", "false"),
                       ("OutMarker", length), ("HiddenLoopStart", 0), ("HiddenLoopEnd", length)):
        _set(c, f"Loop/{tag}", value)
    _set(c, "Name", name)
    _set(c, "Color", color)
    _set(c, "IsWarped", "false")           # plays the file as is: no stretching on stage
    _set(c, "PitchCoarse", 0)
    _set(c, "PitchFine", 0)
    _set(c, "SampleVolume", 1)
    _set(c, "ScrollerTimePreserver/LeftTime", 0)
    _set(c, "ScrollerTimePreserver/RightTime", length)
    fr = c.find("SampleRef/FileRef")
    for tag, value in (("RelativePathType", 1), ("RelativePath", rel_path), ("Path", path), ("Type", 2),
                       ("LivePackName", ""), ("LivePackId", ""), ("OriginalFileSize", size), ("OriginalCrc", 0)):
        _set(fr, tag, value)
    _set(c, "SampleRef/LastModDate", int(mtime))
    _set(c, "SampleRef/DefaultDuration", frames)
    _set(c, "SampleRef/DefaultSampleRate", sr)
    markers = c.find("WarpMarkers")
    for m in list(markers):
        markers.remove(m)
    beat = 1 / 32
    for i, (sec, b) in enumerate(((0.0, 0.0), (beat * 60 / bpm, beat))):
        ET.SubElement(markers, "WarpMarker", {"Id": str(i), "SecTime": repr(sec), "BeatTime": repr(b)})
    ids.renumber(c)
    return c


def _track(proto, ids, track_id, *, name, color, group_id, routing, muted=False):
    t = copy.deepcopy(proto)
    t.set("Id", str(track_id))
    _set(t, "Name/EffectiveName", name)
    _set(t, "Name/UserName", name)
    _set(t, "Color", color)
    _set(t, "TrackGroupId", group_id)
    _set(t, "TrackUnfolded", "true")
    _route(t, routing)
    _set(t, "DeviceChain/Mixer/Speaker/Manual", "false" if muted else "true")
    _set(t, "DeviceChain/Mixer/Volume/Manual", 1)        # mix is printed in the audio: faders at 0 dB
    _set(t, "DeviceChain/Mixer/Pan/Manual", 0)
    for path in ("DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events",
                 "DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events"):
        events = t.find(path)
        if events is not None:
            for e in list(events):
                events.remove(e)
    ids.renumber(t)
    return t


def _midi_clip(proto, env_proto, track, clip_id, *, start, length, name, color, program=None, envelopes=None):
    """A MIDI clip that sends a Program Change when it starts and CC values from envelopes.

    envelopes: {cc: [(time_in_clip_beats, value), ...]}; the first value is the one at
    the clip start. Two events at the same time make a step (as Live writes them).
    """
    c = copy.deepcopy(proto)
    c.set("Id", str(clip_id))
    c.set("Time", repr(start))
    _set(c, "CurrentStart", repr(start))
    _set(c, "CurrentEnd", repr(start + length))
    for tag, value in (("LoopStart", 0), ("LoopEnd", length), ("StartRelative", 0), ("LoopOn", "false"),
                       ("OutMarker", length), ("HiddenLoopStart", 0), ("HiddenLoopEnd", length)):
        _set(c, f"Loop/{tag}", value)
    _set(c, "Name", name)
    _set(c, "Color", color)
    _set(c, "ProgramChange", -1 if program is None else program)
    _set(c, "BankSelectCoarse", -1)
    _set(c, "BankSelectFine", -1)
    holder = c.find("Envelopes/Envelopes")
    for e in list(holder):
        holder.remove(e)
    for n, (cc, points) in enumerate(sorted((envelopes or {}).items())):
        if env_proto is None:
            raise AlsError("La plantilla MIDI no tiene una envolvente de CC para copiar.")
        target = track.find(f"DeviceChain/MainSequencer/MidiControllers/ControllerTargets.{int(cc) + CC_TARGET_OFFSET}")
        if target is None:
            raise AlsError(f"CC {cc} fuera de rango.")
        env = copy.deepcopy(env_proto)
        env.set("Id", str(n))
        env.find("EnvelopeTarget/PointeeId").set("Value", target.get("Id"))
        events = env.find("Automation/Events")
        for e in list(events):
            events.remove(e)
        ET.SubElement(events, "FloatEvent", {"Id": "0", "Time": FOREVER_AGO, "Value": repr(float(points[0][1]))})
        for i, (t, v) in enumerate(points[1:], 1):
            ET.SubElement(events, "FloatEvent", {"Id": str(i), "Time": repr(float(t)), "Value": repr(float(v))})
        holder.append(env)
    return c


def _bar_ceil(beats, bpb):
    return math.ceil(beats / bpb - 1e-9) * bpb


def plan_layout(songs, gap_seconds=30.0):
    """Arrangement start (in beats) of each song, with a gap and starting on a bar."""
    starts, pos, prev_bpm = [], 0.0, None
    for s in songs:
        bpb = int(s["tempo"]["timeSignature"].split("/")[0])
        if prev_bpm is not None:
            pos = _bar_ceil(pos + gap_seconds * prev_bpm / 60.0, bpb)
        starts.append(pos)
        pos = _bar_ceil(pos + s["duration_s"] * s["tempo"]["bpm"] / 60.0, bpb)
        prev_bpm = s["tempo"]["bpm"]
    return starts


def build_set(template_path, songs, als_path, profile="2", gap_seconds=30.0, path_map=None):
    """songs: [{"title", "tempo", "sections", "duration_s", "files": [{"group","label","path","frames","sr"}]}]
    path_map: (local_prefix, real_prefix) to write paths as they are on the user's Mac."""
    if profile not in PROFILES:
        raise AlsError(f"Perfil de salidas desconocido: {profile}")
    tpl = Template(template_path)
    ls = tpl.liveset
    ids = _Ids(max(int(ls.find("NextPointeeId").get("Value")),
                   1 + max(int(e.get("Id")) for e in ls.iter() if "Id" in e.attrib)))
    als_dir = os.path.dirname(os.path.abspath(als_path))

    def real(p):
        p = os.path.abspath(p)
        if path_map and p.startswith(path_map[0]):
            return path_map[1] + p[len(path_map[0]):]
        return p

    starts = plan_layout(songs, gap_seconds)

    # one track per CUES label, per musician, plus the sequence; in order of appearance
    lanes = {"CUES": [], "EN VIVO": [], "SECUENCIA": []}
    for s in songs:
        for f in s["files"]:
            if f["label"] not in lanes[f["group"]]:
                lanes[f["group"]].append(f["label"])

    tracks_el = ls.find("Tracks")
    for t in list(tracks_el):
        tracks_el.remove(t)
    track_id = 1000
    out = PROFILES[profile]
    by_label = {}
    for group in ("CUES", "EN VIVO", "SECUENCIA"):
        if not lanes[group]:
            continue
        gcolor, tcolor = COLORS[group]
        gid = track_id
        track_id += 1
        tracks_el.append(_track(tpl.group_proto, ids, gid, name=group, color=gcolor, group_id=-1,
                                routing=out["cues"] if group == "CUES" else TO_MAIN))
        for label in lanes[group]:
            t = _track(tpl.audio_proto, ids, track_id, name=label, color=tcolor, group_id=gid,
                       routing=TO_GROUP, muted=(group == "EN VIVO"))
            track_id += 1
            tracks_el.append(t)
            by_label[(group, label)] = (t, tcolor)

    midi_lanes = []
    for s in songs:
        for lane in s.get("midi", []):
            if lane["label"] not in midi_lanes:
                midi_lanes.append(lane["label"])
    midi_tracks = {}
    if midi_lanes:
        if tpl.midi_proto is None:
            raise AlsError("Para las pistas MIDI la plantilla necesita una pista MIDI con un clip.")
        gcolor, tcolor = COLORS["CONTROL"]
        gid = track_id
        track_id += 1
        tracks_el.append(_track(tpl.group_proto, ids, gid, name="CONTROL", color=gcolor, group_id=-1, routing=TO_MAIN))
        for label in midi_lanes:
            t = _track(tpl.midi_proto, ids, track_id, name=label, color=tcolor, group_id=gid, routing=TO_GROUP)
            track_id += 1
            tracks_el.append(t)
            midi_tracks[label] = t

    clip_id = 1
    for s, start in zip(songs, starts):
        for lane in s.get("midi", []):
            t = midi_tracks[lane["label"]]
            events = t.find("DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events")
            for ev in lane["events"]:
                events.append(_midi_clip(tpl.midi_clip_proto, tpl.envelope_proto, t, clip_id,
                                         start=start + ev["time"], length=ev["length"], name=ev["name"],
                                         color=COLORS["CONTROL"][1], program=ev.get("program"),
                                         envelopes=ev.get("envelopes")))
                clip_id += 1
        bpm = s["tempo"]["bpm"]
        for f in s["files"]:
            t, color = by_label[(f["group"], f["label"])]
            events = t.find("DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events")
            st = os.stat(f["path"])
            events.append(_clip(tpl.clip_proto, ids, clip_id, start=start, bpm=bpm,
                                seconds=f["frames"] / f["sr"], name=f"{s['title']} · {f['label']}", color=color,
                                path=real(f["path"]), rel_path=os.path.relpath(f["path"], als_dir),
                                frames=f["frames"], sr=f["sr"], size=st.st_size, mtime=st.st_mtime))
            clip_id += 1

    _route(ls.find("MainTrack"), out["main"])
    _tempo_automation(ls, songs, starts)
    _locators(ls, songs, starts)
    _set(ls, "NextPointeeId", ids.next)
    _set(ls, "Transport/CurrentTime", 0)
    _set(ls, "Transport/LoopOn", "false")

    data = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tpl.root, encoding="utf-8")
    with gzip.open(als_path, "wb") as f:
        f.write(data)
    return {"als": als_path, "version": tpl.version, "starts": starts,
            "tracks": [(g, l) for g in lanes for l in lanes[g]] + [("CONTROL", l) for l in midi_lanes],
            "clips": clip_id - 1}


def _tempo_automation(ls, songs, starts):
    main = ls.find("MainTrack")
    tempo = main.find("DeviceChain/Mixer/Tempo")
    _set(tempo, "Manual", songs[0]["tempo"]["bpm"])
    target = tempo.find("AutomationTarget").get("Id")
    env = next((e for e in main.findall("AutomationEnvelopes/Envelopes/AutomationEnvelope")
                if e.find("EnvelopeTarget/PointeeId").get("Value") == target), None)
    if env is None:
        raise AlsError("La plantilla no tiene la automatización de tempo en Main.")
    events = env.find("Automation/Events")
    for e in list(events):
        events.remove(e)
    eid = 0

    def add(time, value):
        nonlocal eid
        ET.SubElement(events, "FloatEvent", {"Id": str(eid), "Time": time, "Value": repr(float(value))})
        eid += 1

    add(FOREVER_AGO, songs[0]["tempo"]["bpm"])
    for prev, s, start in zip(songs, songs[1:], starts[1:]):
        if s["tempo"]["bpm"] != prev["tempo"]["bpm"]:
            add(repr(start), prev["tempo"]["bpm"])      # two events at the same time: a step
            add(repr(start), s["tempo"]["bpm"])


def _locators(ls, songs, starts):
    holder = ls.find("Locators/Locators")
    for e in list(holder):
        holder.remove(e)
    lid = 0

    def add(time, name):
        nonlocal lid
        loc = ET.SubElement(holder, "Locator", {"Id": str(lid)})
        ET.SubElement(loc, "LomId", {"Value": "0"})
        ET.SubElement(loc, "Time", {"Value": repr(float(time))})
        ET.SubElement(loc, "Name", {"Value": name})
        ET.SubElement(loc, "Annotation", {"Value": ""})
        ET.SubElement(loc, "IsSongStart", {"Value": "false"})
        lid += 1

    for n, (s, start) in enumerate(zip(songs, starts), 1):
        bpm = s["tempo"]["bpm"]
        bpb = int(s["tempo"]["timeSignature"].split("/")[0])
        offset = s["tempo"].get("firstDownbeatSec", 0)
        # a click that starts a millisecond in is on the grid: keep locators on the bar lines
        first = start + (offset * bpm / 60.0 if offset > 0.02 else 0.0)
        add(start, f"{n}. {s['title']}")
        for sec in s["sections"][1:]:                     # the first section starts with the song
            add(first + (sec["startBar"] - 1) * bpb, sec["name"])
