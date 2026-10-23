"""LinkCore against a simulated Live that plays, loops and performs quantized jumps."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from SonarStageLink.core import LinkCore  # noqa: E402

Q_BAR = "q_bar"


class Cue:
    def __init__(self, song, name, time):
        self.song, self.name, self.time = song, name, time

    def jump(self):
        if not self.song.is_playing:                # stopped: moves the marker and the playhead
            self.song.current_song_time = self.song.start_time = self.time
            return
        self.song.queued_jump = self.time           # Live waits for the next bar if quantized


class Track:
    def __init__(self, name):
        self.name, self.mute = name, False


class FakeSong:
    """Plays in steps of `dt` beats; honours the arrangement loop and quantized jumps."""

    def __init__(self, cues, bpb=4):
        self.signature_numerator = bpb
        self.tempo = 120.0
        self.is_playing = False
        self.current_song_time = 0.0
        self.loop, self.loop_start, self.loop_length = False, 0.0, 16.0
        self.cue_points = [Cue(self, n, t) for n, t in cues]
        self.tracks = [Track("Click"), Track("Bajo"), Track("Secuencia")]
        self.clip_trigger_quantization = None
        self.start_time = 0.0                       # Live's start marker
        self.queued_jump = None
        self.jumps = []           # (from, to) actually performed

    def start_playing(self):
        self.current_song_time = self.start_time     # as Live does: from the start marker
        self.is_playing = True

    def continue_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False

    def advance(self, beats, dt=0.2):
        """Play forward; jumps fire on the next downbeat (quantization = 1 bar)."""
        for _ in range(int(round(beats / dt))):
            if not self.is_playing:
                return
            old, new = self.current_song_time, self.current_song_time + dt
            if self.queued_jump is not None and self.clip_trigger_quantization == Q_BAR:
                next_bar = (int(old // self.signature_numerator + 1e-9) + 1) * self.signature_numerator
                if new >= next_bar - 1e-9:
                    self.jumps.append((next_bar, self.queued_jump))
                    new = self.queued_jump + (new - next_bar)
                    self.queued_jump = None
            if self.loop and old < self.loop_start + self.loop_length <= new:
                new = self.loop_start + (new - (self.loop_start + self.loop_length))
            self.current_song_time = new


# Two songs as the generator writes them (4/4): song 1 at 0, song 2 at 424 beats
CUES = [("1. Holy Forever", 0), ("Sección 1", 8), ("Sección 2", 24), ("Sección 3", 40),
        ("2. Alegras mis días", 424), ("Sección 1", 432), ("Sección 2", 448)]


def run(core, song, beats):
    for _ in range(int(beats / 0.2)):
        song.advance(0.2)
        core.tick()


@pytest.fixture
def setup():
    song = FakeSong(CUES)
    return LinkCore(song, bar_quantization=Q_BAR), song


def test_structure_and_state(setup):
    core, song = setup
    song.current_song_time = 30.0
    st = core.state()
    assert (st["song"], st["song_title"], st["section"], st["section_bar"], st["section_bars"]) == \
        (1, "Holy Forever", "Sección 2", 2, 4)


def test_goto_waits_for_the_end_of_the_section(setup):
    core, song = setup
    song.current_song_time = 25.0                     # bar 1 of "Sección 2" (24–40)
    song.continue_playing()                           # play from where the test put it
    assert core.handle({"cmd": "goto", "section": "Sección 1"})["state"]["pending"] == "Sección 1"
    run(core, song, 12)                               # still inside the section: nothing yet
    assert song.jumps == []
    run(core, song, 4)                                # crosses into the last bar → fires → lands at 40
    assert song.jumps == [(40, 8)]
    assert core.state()["section"] == "Sección 1"


def test_goto_when_stopped_moves_immediately(setup):
    core, song = setup
    core.handle({"cmd": "goto", "section": "Sección 3"})
    assert song.current_song_time == 40 and core.pending is None


def test_section_names_resolve_within_the_current_song(setup):
    core, song = setup
    song.current_song_time = 430                      # in song 2
    core.handle({"cmd": "goto", "section": "Sección 2"})
    assert song.current_song_time == 448


def test_repeat_plays_the_section_once_more(setup):
    core, song = setup
    song.current_song_time = 26.0                     # in "Sección 2" (24–40)
    song.continue_playing()
    assert core.handle({"cmd": "repeat"})["state"]["pending"] == "Sección 2"
    assert not song.loop                              # no loop: nothing to forget to release
    run(core, song, 16)                               # end of the section → back to its start
    assert song.jumps == [(40, 24)]
    run(core, song, 16)                               # the second time it goes on
    assert core.state()["section"] == "Sección 3" and len(song.jumps) == 1


def test_repeat_twice_by_asking_again(setup):
    core, song = setup
    song.current_song_time = 26.0
    song.continue_playing()
    core.handle({"cmd": "repeat"})
    run(core, song, 16)
    core.handle({"cmd": "repeat"})                    # said again during the repeat
    run(core, song, 16)
    assert song.jumps == [(40, 24), (40, 24)]


def test_release_cancels_a_repeat_and_a_hold(setup):
    core, song = setup
    song.current_song_time = 26.0
    song.continue_playing()
    core.handle({"cmd": "repeat"})
    core.handle({"cmd": "release"})                   # "seguimos": changed our mind
    run(core, song, 16)
    assert song.jumps == [] and core.state()["section"] == "Sección 3"


def test_hold_loops_the_section_until_released(setup):
    core, song = setup
    song.current_song_time = 26.0
    song.continue_playing()
    core.handle({"cmd": "hold"})
    assert (song.loop, song.loop_start, song.loop_length) == (True, 24, 16)
    run(core, song, 20)                               # passes the end of the section: loops back
    assert 24 <= song.current_song_time < 40
    core.handle({"cmd": "release"})
    run(core, song, 16)
    assert core.state()["section"] == "Sección 3"


def test_autostop_at_the_next_song(setup):
    core, song = setup
    song.current_song_time = 420.0
    song.continue_playing()                           # play from where the test put it
    run(core, song, 8)
    assert not song.is_playing and song.current_song_time == 424
    assert core.state()["song"] == 2
    core.handle({"cmd": "play"})                      # one press starts song 2
    assert song.is_playing


def test_jump_across_songs_does_not_autostop(setup):
    core, song = setup
    song.current_song_time = 37.0                     # last bar of "Sección 2" (24–40)
    song.continue_playing()                           # play from where the test put it
    core.handle({"cmd": "goto", "section": "2. Alegras mis días", "any_song": True})
    run(core, song, 4)
    assert song.jumps == [(40, 424)]                  # jumped at the section end…
    assert song.is_playing                            # …and a jump is not "reaching" the next song
    assert core.state()["song"] == 2


def test_next_song_and_mute(setup):
    core, song = setup
    song.current_song_time = 50.0
    core.handle({"cmd": "next_song"})
    assert song.current_song_time == 424
    assert core.handle({"cmd": "mute", "track": "bajo", "on": False})["ok"]
    assert core.handle({"cmd": "mute", "track": "Bajo"})["ok"] and song.tracks[1].mute
    bad = core.handle({"cmd": "mute", "track": "Teclado"})
    assert not bad["ok"] and "Teclado" in bad["error"]


def test_bad_commands_never_raise(setup):
    core, _ = setup
    assert not core.handle({"cmd": "volar"})["ok"]
    assert not core.handle({"cmd": "goto", "section": "Coro"})["ok"]
    assert not core.handle({"cmd": "song"})["ok"]                 # missing number


def test_repeated_names_go_to_the_next_one():
    cues = [("1. Canción", 0), ("Verso", 8), ("Coro", 24), ("Verso", 40), ("Coro", 56), ("Puente", 72)]
    song = FakeSong(cues)
    core = LinkCore(song, bar_quantization=Q_BAR)
    song.current_song_time = 30                       # in the first "Coro"
    core.handle({"cmd": "goto", "section": "Coro"})
    assert song.current_song_time == 56               # the next chorus, not the one we are in
    song.current_song_time = 74                       # in "Puente": no chorus after it
    core.handle({"cmd": "goto", "section": "coro"})
    assert song.current_song_time == 24               # back to the first one


def test_section_word_without_number_finds_numbered_sections():
    cues = [("1. Canción", 0), ("Verso 1", 8), ("Coro 1", 24), ("Verso 2", 40), ("Coro 2", 56)]
    song = FakeSong(cues)
    core = LinkCore(song, bar_quantization=Q_BAR)
    song.current_song_time = 10
    core.handle({"cmd": "goto", "section": "Coro"})
    assert song.current_song_time == 24
    core.handle({"cmd": "goto", "section": "coro"})
    assert song.current_song_time == 56               # the next one, as with repeated names
    core.handle({"cmd": "goto", "section": "Verso 1"})  # an exact name still wins
    assert song.current_song_time == 8


def test_setlist_and_message(setup):
    core, song = setup
    shown = []
    core.notify = shown.append
    r = core.handle({"cmd": "setlist"})
    assert r["setlist"] == [
        {"number": 1, "title": "Holy Forever", "sections": ["Sección 1", "Sección 2", "Sección 3"]},
        {"number": 2, "title": "Alegras mis días", "sections": ["Sección 1", "Sección 2"]}]
    assert r["tracks"] == ["Click", "Bajo", "Secuencia"]
    assert core.handle({"cmd": "message", "text": "Voz: repetir"})["ok"] and shown == ["Voz: repetir"]


def test_play_after_choosing_a_song_starts_that_song(setup):
    # "Secuencia, dale" … "segunda canción" … "dale": must play song 2, not song 1
    core, song = setup
    core.handle({"cmd": "play"})
    run(core, song, 8)
    core.handle({"cmd": "song", "number": 2})
    assert not song.is_playing and song.current_song_time == 424
    core.handle({"cmd": "play"})
    assert song.is_playing and song.current_song_time == 424


class NoStartTime(FakeSong):
    """A Live where the start marker cannot be set from a script."""

    def __setattr__(self, name, value):
        if name == "start_time" and hasattr(self, "start_time"):
            raise AttributeError("read only")
        object.__setattr__(self, name, value)


def test_play_resumes_where_we_parked_even_if_the_marker_is_read_only():
    song = NoStartTime(CUES)
    core = LinkCore(song, bar_quantization=Q_BAR)
    core.handle({"cmd": "song", "number": 2})
    core.handle({"cmd": "play"})                      # Live starts at its marker (0)…
    run(core, song, 0.2)                              # …and the first tick puts it at song 2
    assert song.is_playing and 424 <= song.current_song_time < 425
    core.handle({"cmd": "stop"})
    core.handle({"cmd": "goto", "section": "Sección 2"})        # stopped: moves at once
    core.handle({"cmd": "play"})
    run(core, song, 0.2)
    assert 448 <= song.current_song_time < 449


THREE = [("1. Uno", 0), ("Verso", 8), ("2. Dos", 40), ("Verso", 48), ("3. Tres", 80), ("Verso", 88)]


def test_next_is_changes_what_comes_after_this_song():
    song = FakeSong(THREE)
    core = LinkCore(song, bar_quantization=Q_BAR)
    core.handle({"cmd": "play"})
    run(core, song, 4)
    assert core.state()["next_song"] == "2. Dos"
    r = core.handle({"cmd": "next_is", "number": 3})            # "después va la canción tres"
    assert r["state"]["next_song"] == "3. Tres"
    assert core.handle({"cmd": "setlist"})["order"] == [1, 3, 2]
    run(core, song, 40)                                         # song 1 ends…
    assert not song.is_playing and song.current_song_time == 80  # …and waits at song 3
    core.handle({"cmd": "play"})
    run(core, song, 50)                                         # song 3 is the last arranged…
    core.handle({"cmd": "next_song"})                           # …but 2 is still to be played
    assert song.current_song_time == 40


def test_skip_and_order():
    song = FakeSong(THREE)
    core = LinkCore(song, bar_quantization=Q_BAR)
    core.handle({"cmd": "skip", "number": 2})
    assert core.handle({"cmd": "setlist"})["order"] == [1, 3]
    core.handle({"cmd": "next_song"})                           # from song 1
    assert song.current_song_time == 80
    assert core.handle({"cmd": "order", "songs": [3, 1, 2]})["ok"]
    assert core.state()["next_song"] == "1. Uno"                # in song 3, then 1
    assert not core.handle({"cmd": "order", "songs": [1, 4]})["ok"]
    assert not core.handle({"cmd": "next_is", "number": 9})["ok"]


class ResumesWhereItStopped(FakeSong):
    """The Live seen on stage: after a stop by hand, play went back to where it stopped,
    whatever the playhead and the marker said."""

    def stop_playing(self):
        self.stopped_at = self.current_song_time
        self.is_playing = False

    def start_playing(self):
        self.current_song_time = getattr(self, "stopped_at", self.start_time)
        self.is_playing = True

    continue_playing = start_playing


def test_play_after_choosing_a_song_even_if_live_resumes_elsewhere():
    song = ResumesWhereItStopped(CUES)
    core = LinkCore(song, bar_quantization=Q_BAR)
    song.current_song_time = 440
    song.continue_playing()
    run(core, song, 8)
    song.stop_playing()                               # stopped by hand in song 2
    core.handle({"cmd": "song", "number": 1})          # "Secuencia, canción 1"
    core.handle({"cmd": "play"})                       # "Secuencia, dale"
    run(core, song, 0.4)                               # first ticks
    assert 0 <= song.current_song_time < 1 and core.state()["song"] == 1
    run(core, song, 8)
    assert song.is_playing and core.state()["song"] == 1


def guide_song():
    song = FakeSong(CUES)
    song.tracks.append(Track("Guía"))
    return song, LinkCore(song, bar_quantization=Q_BAR), song.tracks[-1]


def test_smart_guide_is_quiet_until_the_jump_lands():
    song, core, guide = guide_song()
    song.current_song_time = 26.0                     # "Sección 2" (24–40)
    song.continue_playing()
    core.handle({"cmd": "goto", "section": "Sección 1"})
    assert guide.mute                                 # at once: the recording would announce Sección 3
    run(core, song, 12)
    assert guide.mute                                 # still pending
    run(core, song, 4.4)                              # fires, lands at 8
    assert 8 <= song.current_song_time < 12
    run(core, song, 0.4)
    assert not guide.mute and not core.state()["guide_quiet"]


def test_smart_guide_with_repeat_hold_and_cancel():
    song, core, guide = guide_song()
    song.current_song_time = 26.0
    song.continue_playing()
    core.handle({"cmd": "repeat"})
    assert guide.mute
    run(core, song, 16.4)                             # back at the start of the same section
    assert song.jumps == [(40, 24)] and not guide.mute
    core.handle({"cmd": "goto", "section": "Sección 3"})
    core.handle({"cmd": "cancel"})
    assert not guide.mute
    core.handle({"cmd": "hold"})
    run(core, song, 20)
    assert guide.mute                                 # while it loops
    core.handle({"cmd": "release"})
    assert not guide.mute


def test_smart_guide_respects_the_director():
    song, core, guide = guide_song()
    guide.mute = True                                 # muted on purpose
    song.current_song_time = 26.0
    song.continue_playing()
    core.handle({"cmd": "goto", "section": "Sección 1"})
    run(core, song, 20)
    assert guide.mute                                 # we did not mute it, we do not unmute it
    guide.mute = False
    core.handle({"cmd": "goto", "section": "Sección 3"})
    core.handle({"cmd": "mute", "track": "Guía", "on": True})    # "quita la guía" while pending
    run(core, song, 30)
    assert guide.mute                                 # stays as asked


def test_state_says_where_a_jump_fired_in_the_last_bar_lands():
    core, song = LinkCore(FakeSong(CUES), bar_quantization=Q_BAR), None
    song = core.song
    song.current_song_time = 37.0                     # last bar of "Sección 2"
    song.continue_playing()
    st = core.handle({"cmd": "goto", "section": "Sección 1"})["state"]
    assert st["pending"] is None and st["landing"] == "Sección 1"    # fired at once, lands at 40
