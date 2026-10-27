"""Write an Ableton Live set (.als) for a show.

Template-based on purpose: every track, clip and envelope is cloned from a set that
Live itself saved (the user's template), and only names, colors, routing, positions
and file references are changed. The .als format is not documented, so writing
elements from scratch would be guessing; cloning keeps the structure Live expects.
The result declares the template's Live version, so it opens in that version or later.

Layout of the set (docs/plantilla.md):
  CUES       (gray)    → click and guide, to the cue output. With a click template, the
                         click is a MIDI track (Drum Rack) on the tempo map and the
                         pack's audio click stays muted as "Click original". Plus TALKBACK, the
                         director's mic (input monitoring on) so the band hears it
  EN VIVO    (purple)  → one track per musician, muted, to Main
  SECUENCIA  (yellow)  → the summed sequence, to Main
  CONTROL              → one MIDI track per device (pedalboard presets/snapshots,
                         tap tempo for the Apollo console); only when the template has
                         a MIDI track with a clip to clone
Songs go one after another in the arrangement with a gap, each with bar 1 on a bar line.
Clips are unwarped (audio plays untouched, nothing is time-stretched on stage), so the
grid follows the audio instead: the tempo automation is written from each song's tempo
map (grid.py), step by step where the tempo changes. Locators mark each song and its
sections; MIDI clips go on the same grid.
"""
import copy
import gzip
import math
import os
import re
import shutil
import xml.etree.ElementTree as ET

from . import grid

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
TALKBACK = "TALKBACK"
MONITOR_IN = 0                      # MonitoringEnum: 0 In, 1 Auto, 2 Off
TO_MAIN = ("AudioOut/Main", "Main", "")
FOREVER_AGO = "-63072000"           # time Live uses for an envelope's initial value
SNAP_BEATS = 0.05                   # files starting this close before bar 1 start on it


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


def _route(track, routing, which="AudioOutputRouting"):
    r = track.find(f"DeviceChain/{which}")
    if r is None:
        raise AlsError(f"La plantilla no tiene DeviceChain/{which}")
    for tag, value in zip(("Target", "UpperDisplayString", "LowerDisplayString"), routing):
        r.find(tag).set("Value", value)


def mono_input(n):
    """Input routing for interface input n (1-based), as a mono input."""
    return (f"AudioIn/External/M{n - 1}", "Ext. In", str(n))


class Template:
    def __init__(self, path):
        with gzip.open(path) as f:
            self.root = ET.fromstring(f.read())
        self.liveset = self.root.find("LiveSet")
        tracks = list(self.liveset.find("Tracks"))
        self.group_proto = next((t for t in tracks if t.tag == "GroupTrack"), None)
        self.audio_proto = next((t for t in tracks if t.tag == "AudioTrack" and t.find(".//AudioClip") is not None), None)
        # optional: a TALKBACK track in the template brings its devices (a Gate) and fader level
        self.talkback_proto = next((t for t in tracks if t.tag == "AudioTrack"
                                    and t.find("Name/EffectiveName").get("Value").upper() == TALKBACK), None)
        if self.group_proto is None or self.audio_proto is None:
            raise AlsError("La plantilla necesita al menos un grupo y una pista de audio con un clip.")
        self.clip_proto = self.audio_proto.find(".//AudioClip")
        self.midi_proto = next((t for t in tracks if t.tag == "MidiTrack" and t.find(".//MidiClip") is not None), None)
        self.midi_clip_proto = self.midi_proto.find(".//MidiClip") if self.midi_proto is not None else None
        env = self.midi_clip_proto.find("Envelopes/Envelopes/ClipEnvelope") if self.midi_proto is not None else None
        self.envelope_proto = env
        self.version = self.root.get("Creator")


CLICK = "Click"
CLICK_ORIGINAL = "Click original"
CLICK_NOTES = {"accent": 36, "beat": 37}      # pads C1 and C#1 of the click Drum Rack
CLICK_NOTE_LENGTH = 0.25
CLICK_SAMPLES = os.path.join(os.path.dirname(__file__), "assets", "click")
CLICK_FILES = {36: "click-accent.wav", 37: "click-beat.wav"}
VERSION_ATTRS = ("MajorVersion", "MinorVersion", "SchemaChangeCount", "Creator", "Revision")


def _version(creator):
    """'Ableton Live 12.4.3' -> (12, 4, 3)"""
    return tuple(int(n) for n in re.findall(r"\d+", creator or "")[:3])


class ClickTemplate:
    """A set with a MIDI track holding a Drum Rack (the click) and a clip with notes.

    Saved by Live: the track and its device are cloned as they are, and only the samples
    are pointed to SonarStage's own click sounds (assets/click), so every show sounds
    the same whatever the template had in its pads."""

    def __init__(self, path):
        with gzip.open(path) as f:
            self.root = ET.fromstring(f.read())
        tracks = [t for t in self.root.find("LiveSet/Tracks")
                  if t.tag == "MidiTrack" and t.find(".//DrumGroupDevice") is not None]
        if not tracks:
            raise AlsError("La plantilla del click necesita una pista MIDI con un Drum Rack.")
        named = [t for t in tracks if t.find("Name/EffectiveName").get("Value").strip().lower() == "click"]
        self.track = (named or tracks)[0]
        self.clip_proto = next((c for c in self.track.iter("MidiClip") if c.find(".//MidiNoteEvent") is not None), None)
        if self.clip_proto is None:
            raise AlsError("La pista del click en la plantilla necesita un clip con notas.")
        self.version = self.root.get("Creator")


def _click_track(ctpl, ids, track_id, group_id, color, sample_paths):
    """sample_paths: {midi note: (abs path for Live, path relative to the set, file)}"""
    t = _track(ctpl.track, ids, track_id, name=CLICK, color=color, group_id=group_id, routing=TO_GROUP)
    slots = t.find("DeviceChain/MainSequencer/ClipSlotList")
    for slot in (slots if slots is not None else []):
        for holder in slot.iter("Value"):
            for c in list(holder):
                if c.tag == "MidiClip":
                    holder.remove(c)
    for events in t.findall("TakeLanes/TakeLanes/TakeLane/ClipAutomation/Events"):
        for c in list(events):                          # takes recorded in the template, not the show
            events.remove(c)
    for branch in t.iter("DrumBranch"):
        note = branch.find(".//BranchInfo/ReceivingNote")
        key = 128 - int(note.get("Value")) if note is not None else None      # Live stores 128 - note
        if key not in sample_paths:
            continue
        path, rel, local = sample_paths[key]
        info = sf_info(local)
        st = os.stat(local)
        for ref in branch.iter("SampleRef"):
            fr = ref.find("FileRef")
            for tag, value in (("RelativePathType", 1), ("RelativePath", rel), ("Path", path), ("Type", 2),
                               ("LivePackName", ""), ("LivePackId", ""), ("OriginalFileSize", st.st_size),
                               ("OriginalCrc", 0)):
                if fr.find(tag) is not None:
                    _set(fr, tag, value)
            _set(ref, "LastModDate", int(st.st_mtime))
            _set(ref, "DefaultDuration", info[0])
            _set(ref, "DefaultSampleRate", info[1])
    return t


def sf_info(path):
    """(frames, sample rate) of a WAV, without extra dependencies."""
    import wave
    with wave.open(path) as w:
        return w.getnframes(), w.getframerate()


def _click_clip(proto, ids, clip_id, *, start, beats, bpb, name, color):
    """One clip per song: a note on every beat the song's click plays (beats from its bar 1);
    the accent on beat 1 of each bar."""
    first, last = min(beats), max(beats)
    length = float(last - first + 1)
    c = copy.deepcopy(proto)
    c.set("Id", str(clip_id))
    c.set("Time", repr(float(start + first)))
    _set(c, "CurrentStart", repr(float(start + first)))
    _set(c, "CurrentEnd", repr(float(start + first + length)))
    for tag, value in (("LoopStart", 0), ("LoopEnd", length), ("StartRelative", 0), ("LoopOn", "false"),
                       ("OutMarker", length), ("HiddenLoopStart", 0), ("HiddenLoopEnd", length)):
        _set(c, f"Loop/{tag}", value)
    _set(c, "Name", name)
    _set(c, "Color", color)
    # a groove points into the template's groove pool, which the show does not have:
    # Live refuses the whole set ("damaged") over that dangling reference
    groove = c.find("GrooveSettings/GrooveId")
    if groove is not None:
        groove.set("Value", "-1")
    keytracks = c.find("Notes/KeyTracks")
    kt_proto = copy.deepcopy(keytracks.find("KeyTrack"))
    ev_proto = kt_proto.find("Notes/MidiNoteEvent")
    for kt in list(keytracks):
        keytracks.remove(kt)
    note_id = 1
    for n, key in enumerate((CLICK_NOTES["accent"], CLICK_NOTES["beat"]), 1):
        hits = [b for b in beats if (b % bpb == 0) == (key == CLICK_NOTES["accent"])]
        if not hits:
            continue
        kt = copy.deepcopy(kt_proto)
        kt.set("Id", str(n))
        notes = kt.find("Notes")
        for e in list(notes):
            notes.remove(e)
        for b in hits:
            ev = copy.deepcopy(ev_proto)
            ev.attrib.update({"Time": repr(float(b - first)), "Duration": repr(CLICK_NOTE_LENGTH),
                              "Velocity": "100", "NoteId": str(note_id)})
            note_id += 1
            notes.append(ev)
        _set(kt, "MidiKey", key)
        keytracks.append(kt)
    gen = c.find("Notes/NoteIdGenerator/NextId")
    if gen is not None:
        gen.set("Value", str(note_id))
    ids.renumber(c)
    return c


def _clip(proto, ids, clip_id, *, start, bpm, length, name, color, path, rel_path, frames, sr, size, mtime):
    """length: beats the file lasts on the show's tempo automation."""
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


def _track(proto, ids, track_id, *, name, color, group_id, routing, muted=False, keep_level=False):
    t = copy.deepcopy(proto)
    t.set("Id", str(track_id))
    _set(t, "Name/EffectiveName", name)
    _set(t, "Name/UserName", name)
    _set(t, "Color", color)
    _set(t, "TrackGroupId", group_id)
    _set(t, "TrackUnfolded", "true")
    _route(t, routing)
    _set(t, "DeviceChain/Mixer/Speaker/Manual", "false" if muted else "true")
    if not keep_level:
        _set(t, "DeviceChain/Mixer/Volume/Manual", 1)    # mix is printed in the audio: faders at 0 dB
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
    """Arrangement beat of bar 1 of each song: on a bar line, after the previous song and a gap.

    A song's files may start a little before its bar 1 (clicks or a pickup before it);
    the gap is counted from where the previous files end, at that song's last tempo.
    """
    downs, end, prev_bpm = [], None, None
    for s in songs:
        g = grid.Grid(s["tempo"])
        pre = _pre_beats(s)
        pos = 0.0 if end is None else end + gap_seconds * prev_bpm / 60.0
        down = _bar_ceil(pos - pre, g.bpb)
        downs.append(down)
        end = down + g.beat(s["duration_s"])
        prev_bpm = g.last_bpm
    return downs


def _pre_beats(s):
    """Where the song's files start, in beats from its bar 1 (0 or negative).

    A click a few ms into the file (real packs: 1 ms) counts as starting on bar 1, so
    songs do not gain an empty bar and clips start on the bar line."""
    pre = grid.Grid(s["tempo"]).beat(0.0)
    return 0.0 if -SNAP_BEATS < pre <= 0 else pre


def _song_start(s, down):
    """Where the song's files start in the arrangement (beats)."""
    return down + _pre_beats(s)


def build_set(template_path, songs, als_path, profile="2", gap_seconds=30.0, path_map=None, talkback=None,
              click_template=None):
    """songs: [{"title", "tempo", "sections", "duration_s", "files": [{"group","label","path","frames","sr"}],
               "click_beats": [beats from bar 1 where the click plays] (optional)}]
    path_map: (local_prefix, real_prefix) to write paths as they are on the user's Mac.
    talkback: interface input (1, 2, …) of the director's mic, or None for no TALKBACK track.
    click_template: set with the click Drum Rack (ClickTemplate); with it, the click is MIDI
    and the audio click is kept muted as "Click original". The set declares the newer of
    the two templates' Live versions."""
    if profile not in PROFILES:
        raise AlsError(f"Perfil de salidas desconocido: {profile}")
    if talkback is not None and (not isinstance(talkback, int) or talkback < 1):
        raise AlsError(f"Entrada del talkback no válida: {talkback}")
    tpl = Template(template_path)
    ctpl = ClickTemplate(click_template) if click_template else None
    midi_click = ctpl is not None and any(s.get("click_beats") for s in songs)
    if midi_click and _version(ctpl.version) > _version(tpl.version):
        for a in VERSION_ATTRS:
            if ctpl.root.get(a) is not None:
                tpl.root.set(a, ctpl.root.get(a))
        tpl.version = ctpl.version
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
    click_track = None
    for group in ("CUES", "EN VIVO", "SECUENCIA"):
        if not lanes[group] and not (group == "CUES" and (talkback or midi_click)):
            continue
        gcolor, tcolor = COLORS[group]
        gid = track_id
        track_id += 1
        tracks_el.append(_track(tpl.group_proto, ids, gid, name=group, color=gcolor, group_id=-1,
                                routing=out["cues"] if group == "CUES" else TO_MAIN))
        if group == "CUES" and midi_click:
            samples = {}
            sample_dir = os.path.join(als_dir, "Audio", "Click")
            os.makedirs(sample_dir, exist_ok=True)
            for key, name in CLICK_FILES.items():
                local = os.path.join(sample_dir, name)
                shutil.copyfile(os.path.join(CLICK_SAMPLES, name), local)
                samples[key] = (real(local), os.path.relpath(local, als_dir), local)
            click_track = _click_track(ctpl, ids, track_id, gid, tcolor, samples)
            track_id += 1
            tracks_el.append(click_track)
        for label in lanes[group]:
            # with the MIDI click, the pack's click stays as a muted backup
            original_click = group == "CUES" and label == CLICK and midi_click
            t = _track(tpl.audio_proto, ids, track_id, name=CLICK_ORIGINAL if original_click else label,
                       color=tcolor, group_id=gid, routing=TO_GROUP,
                       muted=(group == "EN VIVO") or original_click)
            track_id += 1
            tracks_el.append(t)
            by_label[(group, label)] = (t, tcolor)
        if group == "CUES" and talkback:
            # no clips: it only passes the mic through (monitor In) to the cue output, at the
            # template's level if the template has its own TALKBACK track, otherwise at 0 dB
            proto = tpl.talkback_proto if tpl.talkback_proto is not None else tpl.audio_proto
            t = _track(proto, ids, track_id, name=TALKBACK, color=tcolor, group_id=gid,
                       routing=TO_GROUP, keep_level=tpl.talkback_proto is not None)
            track_id += 1
            _route(t, mono_input(talkback), "AudioInputRouting")
            _set(t, "DeviceChain/MainSequencer/MonitoringEnum", MONITOR_IN)
            tracks_el.append(t)

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
    for s, start in zip(songs, starts):                   # start: bar 1 of the song (MIDI times count from it)
        for lane in s.get("midi", []):
            t = midi_tracks[lane["label"]]
            events = t.find("DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events")
            for ev in lane["events"]:
                events.append(_midi_clip(tpl.midi_clip_proto, tpl.envelope_proto, t, clip_id,
                                         start=start + ev["time"], length=ev["length"], name=ev["name"],
                                         color=COLORS["CONTROL"][1], program=ev.get("program"),
                                         envelopes=ev.get("envelopes")))
                clip_id += 1
        g = grid.Grid(s["tempo"])
        if click_track is not None and s.get("click_beats"):
            click_track.find("DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events").append(
                _click_clip(ctpl.clip_proto, ids, clip_id, start=start, beats=s["click_beats"], bpb=g.bpb,
                            name=f"{s['title']} · Click", color=COLORS["CUES"][1]))
            clip_id += 1
        file_start = _song_start(s, start)
        for f in s["files"]:
            t, color = by_label[(f["group"], f["label"])]
            events = t.find("DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events")
            st = os.stat(f["path"])
            events.append(_clip(tpl.clip_proto, ids, clip_id, start=file_start, bpm=g.first_bpm,
                                length=g.beat(f["frames"] / f["sr"]) - g.beat(0.0),
                                name=f"{s['title']} · {f['label']}", color=color,
                                path=real(f["path"]), rel_path=os.path.relpath(f["path"], als_dir),
                                frames=f["frames"], sr=f["sr"], size=st.st_size, mtime=st.st_mtime))
            clip_id += 1

    _route(ls.find("MainTrack"), out["main"])
    _tempo_automation(ls, songs, starts)
    _locators(ls, songs, starts)
    _set(ls, "NextPointeeId", ids.next)
    _set(ls, "Transport/CurrentTime", 0)
    _set(ls, "Transport/LoopOn", "false")

    _check_references(ls)
    data = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tpl.root, encoding="utf-8")
    with gzip.open(als_path, "wb") as f:
        f.write(data)
    def names(g):
        out_names = ([CLICK] if g == "CUES" and midi_click else [])
        out_names += [CLICK_ORIGINAL if g == "CUES" and l == CLICK and midi_click else l for l in lanes[g]]
        return out_names + ([TALKBACK] if g == "CUES" and talkback else [])

    return {"als": als_path, "version": tpl.version, "starts": starts,
            "tracks": [(g, l) for g in lanes for l in names(g)] + [("CONTROL", l) for l in midi_lanes],
            "midi_click": midi_click,
            "talkback_from_template": talkback is not None and tpl.talkback_proto is not None,
            "clips": clip_id - 1}


def _check_references(ls):
    """References Live resolves when opening: a dangling one makes it call the set damaged."""
    targets = {e.get("Id") for e in ls.iter() if "Id" in e.attrib and (
        e.tag == "Pointee" or e.tag.endswith("Target") or e.tag.startswith("ControllerTargets."))}
    dangling = sorted({e.get("Value") for e in ls.iter("PointeeId")} - targets)
    if dangling:
        raise AlsError(f"Referencias rotas a parámetros: {dangling[:5]}")
    pool = ls.find("GroovePool")
    grooves = {g.get("Id") for g in pool.iter("Groove")} if pool is not None else set()
    missing = sorted({e.get("Value") for e in ls.iter("GrooveId")} - grooves - {"-1"})
    if missing:
        raise AlsError(f"Clips con un groove que no está en el set: {missing}")


def _tempo_automation(ls, songs, starts):
    """Each song's tempo map as steps: its first tempo from where its files start, then
    every change on its beat. Between songs the last tempo holds through the gap."""
    grids = [grid.Grid(s["tempo"]) for s in songs]
    main = ls.find("MainTrack")
    tempo = main.find("DeviceChain/Mixer/Tempo")
    _set(tempo, "Manual", grids[0].first_bpm)
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

    current = grids[0].first_bpm
    add(FOREVER_AGO, current)
    for s, g, down in zip(songs, grids, starts):
        for n, (beat, bpm) in enumerate(g.steps()):
            at = _song_start(s, down) if n == 0 else down + beat
            if bpm != current:
                add(repr(float(at)), current)          # two events at the same time: a step
                add(repr(float(at)), bpm)
                current = bpm


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

    for n, (s, down) in enumerate(zip(songs, starts), 1):
        bpb = grid.Grid(s["tempo"]).bpb
        file_start = _song_start(s, down)
        add(file_start, f"{n}. {s['title']}")
        for sec in s["sections"][1:]:                     # the first section starts with the song
            add(down + (sec["startBar"] - 1) * bpb, sec["name"])
