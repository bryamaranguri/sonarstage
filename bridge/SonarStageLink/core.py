"""SonarStage Link: show logic, independent of Ableton so it can be tested.

`song` is Live's Song object (or a fake with the same attributes):
  is_playing, current_song_time, tempo, signature_numerator,
  loop, loop_start, loop_length, cue_points (.name, .time, .jump()),
  tracks (.name, .mute), start_playing(), stop_playing(), continue_playing(),
  clip_trigger_quantization.

Songs and sections come from the show's locators: a locator named "<n>. <title>" opens
a song (and its first section); every other locator opens a section.

Timing rules, so changes land exactly on the beat without the script's 100 ms tick
deciding when:
- Repeat a section: Live's own arrangement loop is set to the section.
- Go to another section: the jump is armed and fired during the last bar of the
  current section through the locator's jump(), with global quantization at one bar,
  so Live performs it on the next downbeat, which is where the section ends.
"""
import re

SONG_LOCATOR = re.compile(r"^\s*(\d+)\.\s+(.+)$")


class Section(object):
    def __init__(self, cue, song_index, song_title, is_song_start):
        self.cue = cue
        self.name = cue.name
        self.start = cue.time
        self.end = None
        self.song_index = song_index
        self.song_title = song_title
        self.is_song_start = is_song_start


class LinkCore(object):
    def __init__(self, song, bar_quantization=None, log=None):
        self.song = song
        self.bar_quantization = bar_quantization      # Live.Song.Quantization.q_bar inside Live
        self.log = log or (lambda msg: None)
        self.pending = None                           # Section to jump to
        self.autostop = True
        self._last_beat = None
        self.sections = []
        self.refresh()

    # --- structure ---------------------------------------------------------------------

    def refresh(self):
        cues = sorted(self.song.cue_points, key=lambda c: c.time)
        sections, song_index, song_title = [], 0, None
        for cue in cues:
            m = SONG_LOCATOR.match(cue.name)
            if m:
                song_index, song_title = int(m.group(1)), m.group(2)
            sections.append(Section(cue, song_index, song_title, bool(m)))
        for a, b in zip(sections, sections[1:]):
            a.end = b.start
        if sections:
            sections[-1].end = float("inf")
        self.sections = sections

    def bar_length(self):
        return float(self.song.signature_numerator)

    def section_at(self, beat):
        current = None
        for s in self.sections:
            if s.start <= beat + 1e-6:
                current = s
            else:
                break
        return current

    def song_starts(self):
        return [s for s in self.sections if s.is_song_start]

    def find_section(self, name, within_song=None, after=None):
        """Section by name. Names repeat ("Coro" several times): the first one after `after`
        (the current position) wins, else the first one in the song."""
        key = name.strip().lower()
        matches = [s for s in self.sections if s.name.lower() == key
                   and (within_song is None or s.song_index == within_song)]
        if not matches:
            return None
        if after is not None:
            later = [s for s in matches if s.start > after + 1e-6]
            if later:
                return later[0]
        return matches[0]

    # --- commands ----------------------------------------------------------------------

    def handle(self, msg):
        cmd = msg.get("cmd")
        try:
            if cmd == "status":
                pass
            elif cmd == "refresh":
                self.refresh()
            elif cmd == "play":
                self.song.continue_playing() if msg.get("continue") else self.song.start_playing()
            elif cmd == "stop":
                self.song.stop_playing()
                self.pending = None
            elif cmd == "goto":
                self._goto(msg)
            elif cmd == "next_section":
                self._relative(+1)
            elif cmd == "repeat":
                self._repeat()
            elif cmd == "release":
                self.song.loop = False
            elif cmd == "cancel":
                self.pending = None
            elif cmd == "song":
                self._song(int(msg["number"]))
            elif cmd == "next_song":
                self._next_song()
            elif cmd == "mute":
                self._mute(msg["track"], bool(msg.get("on", True)))
            elif cmd == "autostop":
                self.autostop = bool(msg.get("on", True))
            else:
                return {"ok": False, "error": "comando desconocido: %s" % cmd, "state": self.state()}
        except Exception as e:      # never let a bad message break the show
            self.log("SonarStageLink: %r -> %r" % (msg, e))
            return {"ok": False, "error": str(e), "state": self.state()}
        return {"ok": True, "state": self.state()}

    def _goto(self, msg):
        current = self.section_at(self.song.current_song_time)
        within = current.song_index if current and not msg.get("any_song") else None
        target = self.find_section(msg["section"], within, after=current.start if current else None)
        if target is None:
            raise ValueError("no hay una sección llamada %r" % msg["section"])
        self._arm(target)

    def _relative(self, step):
        current = self.section_at(self.song.current_song_time)
        if current is None:
            raise ValueError("no hay secciones")
        i = self.sections.index(current) + step
        if not 0 <= i < len(self.sections):
            raise ValueError("no hay más secciones")
        self._arm(self.sections[i])

    def _arm(self, target):
        if not self.song.is_playing:
            self.song.current_song_time = target.start
            self.pending = None
            return
        self.song.loop = False
        self.pending = target
        self._maybe_fire()

    def _repeat(self):
        current = self.section_at(self.song.current_song_time)
        if current is None or current.end == float("inf"):
            raise ValueError("no hay una sección que repetir")
        self.pending = None
        self.song.loop_start = current.start
        self.song.loop_length = current.end - current.start
        self.song.loop = True

    def _song(self, number):
        starts = [s for s in self.song_starts() if s.song_index == number]
        if not starts:
            raise ValueError("no hay canción %d" % number)
        self.song.loop = False
        self.pending = None
        if self.song.is_playing:
            self.song.stop_playing()
        self.song.current_song_time = starts[0].start

    def _next_song(self):
        current = self.section_at(self.song.current_song_time)
        nxt = [s for s in self.song_starts() if current is None or s.song_index > current.song_index]
        if not nxt:
            raise ValueError("es la última canción")
        self._song(nxt[0].song_index)

    def _mute(self, name, on):
        key = name.strip().lower()
        for t in self.song.tracks:
            if t.name.strip().lower() == key:
                t.mute = on
                return
        raise ValueError("no hay una pista llamada %r" % name)

    # --- every tick (~100 ms) ----------------------------------------------------------

    def tick(self):
        beat = self.song.current_song_time
        if self.song.is_playing:
            self._maybe_fire()
            # natural playback only: a jump also crosses positions, but in one step
            moving_on = self._last_beat is not None and 0 <= beat - self._last_beat < 2 * self.bar_length()
            if self.autostop and moving_on:
                for s in self.song_starts():
                    if self._last_beat < s.start - 1e-6 <= beat and s.start > 0:
                        # reached the next song: stop and wait there
                        self.song.stop_playing()
                        self.song.loop = False
                        self.pending = None
                        self.song.current_song_time = s.start
                        beat = s.start
                        break
        self._last_beat = beat

    def _maybe_fire(self):
        if self.pending is None:
            return
        beat = self.song.current_song_time
        current = self.section_at(beat)
        if current is None:
            return
        last_bar = current.end - self.bar_length()
        if beat >= last_bar - 1e-6 or current.end == float("inf"):
            if self.bar_quantization is not None:
                self.song.clip_trigger_quantization = self.bar_quantization
            target, self.pending = self.pending, None
            target.cue.jump()                 # Live performs it on the next downbeat

    # --- state -------------------------------------------------------------------------

    def state(self):
        beat = self.song.current_song_time
        current = self.section_at(beat)
        bar = self.bar_length()
        return {
            "playing": bool(self.song.is_playing),
            "beat": round(beat, 3),
            "tempo": round(self.song.tempo, 3),
            "song": current.song_index if current else None,
            "song_title": current.song_title if current else None,
            "section": current.name if current else None,
            "section_bar": int((beat - current.start) // bar) + 1 if current else None,
            "section_bars": None if not current or current.end == float("inf")
            else int(round((current.end - current.start) / bar)),
            "loop": bool(self.song.loop),
            "pending": self.pending.name if self.pending else None,
            "autostop": self.autostop,
        }
