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
        self.queued_jump = None
        self.jumps = []           # (from, to) actually performed

    def start_playing(self):
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
    song.start_playing()
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


def test_repeat_loops_the_section_until_released(setup):
    core, song = setup
    song.current_song_time = 26.0
    song.start_playing()
    core.handle({"cmd": "repeat"})
    assert (song.loop, song.loop_start, song.loop_length) == (True, 24, 16)
    run(core, song, 20)                               # passes the end of the section: loops back
    assert 24 <= song.current_song_time < 40
    core.handle({"cmd": "release"})
    run(core, song, 16)
    assert core.state()["section"] == "Sección 3"


def test_autostop_at_the_next_song(setup):
    core, song = setup
    song.current_song_time = 420.0
    song.start_playing()
    run(core, song, 8)
    assert not song.is_playing and song.current_song_time == 424
    assert core.state()["song"] == 2
    core.handle({"cmd": "play"})                      # one press starts song 2
    assert song.is_playing


def test_jump_across_songs_does_not_autostop(setup):
    core, song = setup
    song.current_song_time = 37.0                     # last bar of "Sección 2" (24–40)
    song.start_playing()
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
