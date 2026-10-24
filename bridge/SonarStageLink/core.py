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
- Repeat a section once: the same armed jump, back to the start of the section. Saying
  it again during the repeat repeats it again.
- Hold a section (repeat until released): Live's own arrangement loop.
- Smart guide: while a jump is pending, a hold is on, or until a jump has landed, the
  guide track is muted, so it does not announce the section the recording had next.
  It comes back by itself.
- Go to another section: the jump is armed and fired during the last bar of the
  current section through the locator's jump(), with global quantization at one bar,
  so Live performs it on the next downbeat, which is where the section ends.
"""
import re

SONG_LOCATOR = re.compile(r"^\s*(\d+)\.\s+(.+)$")
TRAILING_NUMBER = re.compile(r"\s+\d+$")
GUIDE_NAMES = {"guía", "guia", "guide", "cues", "cue"}


def base_name(name):
    """'Coro 2' -> 'coro': the section word without its number."""
    return TRAILING_NUMBER.sub("", name.strip().lower())


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
    def __init__(self, song, bar_quantization=None, log=None, notify=None):
        self.song = song
        self.bar_quantization = bar_quantization      # Live.Song.Quantization.q_bar inside Live
        self.log = log or (lambda msg: None)
        self.notify = notify or (lambda msg: None)    # Live's status bar
        self.pending = None                           # Section to jump to
        self.parked = None                            # where we left the stopped transport
        self.order = None                             # play order (song numbers); None = as arranged
        self.verify_start = None                      # where the last play had to start
        self.landing = None                           # (target, beat it was fired at)
        self.guide_quieted = []                       # guide tracks muted by the smart guide
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
        (the current position) wins, else the first one in the song. Without an exact
        match, "Coro" also finds "Coro 1" and "Coro 2"."""
        key = name.strip().lower()
        pool = [s for s in self.sections if within_song is None or s.song_index == within_song]
        matches = [s for s in pool if s.name.lower() == key]
        if not matches:
            matches = [s for s in pool if base_name(s.name) == key]
        if not matches:
            return None
        if after is not None:
            later = [s for s in matches if s.start > after + 1e-6]
            if later:
                return later[0]
        return matches[0]

    def play_order(self):
        numbers = [s.song_index for s in self.song_starts()]
        if not self.order:
            return numbers
        return [n for n in self.order if n in numbers]

    def next_song_number(self, current):
        """The song after `current` in the play order (None after the last one)."""
        order = self.play_order()
        if current in order:
            i = order.index(current)
            return order[i + 1] if i + 1 < len(order) else None
        later = [n for n in order if n > current]      # a song played outside the order
        return later[0] if later else None

    def _song_number(self, msg):
        n = int(msg["number"])
        if n not in [s.song_index for s in self.song_starts()]:
            raise ValueError("no hay canción %d" % n)
        return n

    def _next_is(self, n):
        """Song `n` goes right after the current one."""
        current = self.section_at(self.song.current_song_time)
        order = [x for x in self.play_order() if x != n]
        at = order.index(current.song_index) + 1 if current and current.song_index in order else 0
        order.insert(at, n)
        self.order = order

    def setlist(self):
        songs = []
        for s in self.sections:
            if s.is_song_start or not songs:
                songs.append({"number": s.song_index, "title": s.song_title, "sections": []})
            if not s.is_song_start:
                songs[-1]["sections"].append(s.name)
        return songs

    # --- commands ----------------------------------------------------------------------

    def handle(self, msg):
        cmd = msg.get("cmd")
        try:
            if cmd == "status":
                pass
            elif cmd == "refresh":
                self.refresh()
            elif cmd == "play":
                self._play(msg)
            elif cmd == "stop":
                self.song.stop_playing()
                self.pending = None
            elif cmd == "goto":
                self._goto(msg)
            elif cmd == "next_section":
                self._relative(+1)
            elif cmd == "repeat":
                self._repeat()
            elif cmd == "hold":
                self._hold()
            elif cmd == "release":
                self.song.loop = False
                self.pending = None
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
            elif cmd == "order":
                numbers = [s.song_index for s in self.song_starts()]
                order = [int(n) for n in msg["songs"]]
                bad = [n for n in order if n not in numbers]
                if bad:
                    raise ValueError("no hay canción %d" % bad[0])
                self.order = order
            elif cmd == "next_is":
                self._next_is(self._song_number(msg))
            elif cmd == "skip":
                n = self._song_number(msg)
                self.order = [x for x in self.play_order() if x != n]
            elif cmd == "setlist":
                return {"ok": True, "setlist": self.setlist(), "order": self.play_order(),
                        "tracks": [t.name for t in self.song.tracks],
                        "mutes": {t.name: bool(t.mute) for t in self.song.tracks}, "state": self.state()}
            elif cmd == "message":
                self.notify(str(msg.get("text", ""))[:120])
            else:
                return {"ok": False, "error": "comando desconocido: %s" % cmd, "state": self.state()}
        except Exception as e:      # never let a bad message break the show
            self.log("%r -> error: %r" % (msg, e))
            return {"ok": False, "error": str(e), "state": self.state()}
        self._smart_guide()
        if cmd not in ("status", "setlist", "refresh"):
            self.log("%r -> ok" % (msg,))         # Log.txt shows what each command did
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

    def _park(self, beat):
        """Leave the stopped transport at `beat`, so the next play starts there.

        Live does not always start where the playhead shows: play starts at the start
        marker, and after a stop by hand it resumed where it had stopped (seen on stage,
        22 Oct). So everything is moved: the locator there is "clicked" (jump, which moves
        the marker while stopped), the playhead and the marker are set, and _play checks
        on the first tick that playback really started here."""
        cue = next((x.cue for x in self.sections if abs(x.start - beat) < 1e-6), None)
        if cue is not None and not self.song.is_playing:
            try:
                cue.jump()
            except Exception as e:
                self.log("jump al locator: %r" % (e,))
        self.song.current_song_time = beat
        try:
            self.song.start_time = beat
        except Exception:
            pass                                  # read only in some versions: _play checks
        self.parked = beat

    def _play(self, msg):
        if self.song.is_playing:
            return
        if self.parked is not None:
            beat, self.parked = self.parked, None
            self.song.current_song_time = beat
            self.song.start_playing()
            self.verify_start = beat              # tick() puts it right if Live started elsewhere
        elif msg.get("continue"):
            self.song.continue_playing()
        else:
            self.song.start_playing()

    def _check_start(self, beat):
        """First tick after a play from a chosen place: if Live started somewhere else, go
        there at once (a few ms of the wrong place are better than the wrong song)."""
        target, self.verify_start = self.verify_start, None
        if not target - 1e-6 <= beat < target + 2 * self.bar_length():
            self.log("play empezó en %.2f en vez de %.2f: corrigiendo" % (beat, target))
            self.song.current_song_time = target
            return target
        return beat

    def _arm(self, target):
        if not self.song.is_playing:
            self._park(target.start)
            self.pending = None
            return
        self.song.loop = False
        self.pending = target
        self._maybe_fire()

    def _repeat(self):
        current = self.section_at(self.song.current_song_time)
        if current is None or current.end == float("inf"):
            raise ValueError("no hay una sección que repetir")
        self._arm(current)

    def _hold(self):
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
        self._park(starts[0].start)

    def _next_song(self):
        current = self.section_at(self.song.current_song_time)
        n = self.play_order()[0] if current is None else self.next_song_number(current.song_index)
        if n is None:
            raise ValueError("es la última canción")
        self._song(n)

    def _mute(self, name, on):
        key = name.strip().lower()
        for t in self.song.tracks:
            if t.name.strip().lower() == key:
                if t in self.guide_quieted:
                    self.guide_quieted.remove(t)      # what the director asks for wins
                t.mute = on
                return
        raise ValueError("no hay una pista llamada %r" % name)

    # --- every tick (~100 ms) ----------------------------------------------------------

    def tick(self):
        beat = self.song.current_song_time
        if self.song.is_playing and self.verify_start is not None:
            beat = self._check_start(beat)
            self._last_beat = beat
        if self.song.is_playing:
            self._maybe_fire()
            # natural playback only: a jump also crosses positions, but in one step
            moving_on = self._last_beat is not None and 0 <= beat - self._last_beat < 2 * self.bar_length()
            if self.autostop and moving_on:
                for s in self.song_starts():
                    if self._last_beat < s.start - 1e-6 <= beat and s.start > 0:
                        # end of a song: stop and wait at the next one in the play order
                        finished = self.section_at(self._last_beat)
                        n = self.next_song_number(finished.song_index) if finished else None
                        starts = [x for x in self.song_starts() if x.song_index == n]
                        target = starts[0].start if starts else s.start
                        self.song.stop_playing()
                        self.song.loop = False
                        self.pending = None
                        self._park(target)
                        beat = target
                        break
        self._check_landing(beat)
        self._smart_guide()
        self._last_beat = beat

    def _check_landing(self, beat):
        if self.landing is None:
            return
        target, fired = self.landing
        bar = self.bar_length()
        landed = target.start - 1e-6 <= beat < target.start + bar and (beat < fired or target.start >= fired)
        if landed or beat >= fired + 2 * bar or not self.song.is_playing:
            self.landing = None

    def _smart_guide(self):
        want = bool(self.song.is_playing and (self.pending is not None or self.song.loop
                                              or self.landing is not None))
        if want and not self.guide_quieted:
            for t in self.song.tracks:
                if t.name.strip().lower() in GUIDE_NAMES and not t.mute:
                    t.mute = True
                    self.guide_quieted.append(t)
        elif not want and self.guide_quieted:
            for t in self.guide_quieted:
                t.mute = False
            self.guide_quieted = []

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
            self.landing = (target, beat)
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
            # where a jump fired in this last bar will land (no longer "pending")
            "landing": self.landing[0].name if self.landing else None,
            "autostop": self.autostop,
            "next_song": self._next_title(current),
            "guide_quiet": bool(self.guide_quieted),
        }

    def _next_title(self, current):
        n = self.play_order()[0] if current is None else self.next_song_number(current.song_index)
        starts = [s for s in self.song_starts() if s.song_index == n]
        return "%d. %s" % (n, starts[0].song_title) if starts else None
