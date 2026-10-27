"""Tempo map from the click: numbering beats, fitting segments, beat <-> second."""
import numpy as np
import pytest

from sonarstage_import import grid


def test_constant_song_is_one_round_segment():
    rng = np.random.default_rng(0)
    beats = np.arange(600) * 60 / 128 + 0.2 + rng.normal(0, 0.0009, 600)   # ~1 ms detection jitter
    tmap, stats = grid.tempo_map(beats, downbeat=2)
    assert len(tmap) == 1 and tmap[0]["bpm"] == 128.0 and tmap[0]["beat"] == -2
    assert stats["max_error_ms"] <= grid.TOLERANCE_S * 1000 and stats["silent_beats"] == 0


def ritardando_and_stop():
    t = list(np.arange(200) * 60 / 72)
    last = t[-1]
    for i in range(1, 9):                  # slows from 72 to 60 over 8 beats
        last += 60 / (72 - 12 * i / 8)
        t.append(last)
    last += 3.1                            # a stop: no click for 3.1 s
    t.append(last)
    t += [last + i * 60 / 72 for i in range(1, 100)]
    return np.array(t)


def test_ritardando_and_stop_follow_every_beat():
    beats = ritardando_and_stop()
    tmap, stats = grid.tempo_map(beats)
    assert tmap[0] == {"beat": 0, "sec": 0.0, "bpm": 72.0}
    assert tmap[-1]["bpm"] == 72.0 and len(tmap) > 5
    assert stats["silent_beats"] > 0
    nums, kept = grid.number_beats(beats)
    g = grid.Grid({"bpm": 72, "timeSignature": "4/4", "map": tmap})
    assert np.max(np.abs([g.sec(n) for n in nums] - kept)) <= grid.TOLERANCE_S + 1e-9


def test_slower_tempo_is_not_a_stop():
    t = list(np.arange(40) * 0.5)          # 120 bpm…
    t += [t[-1] + (i + 1) * 1.0 for i in range(40)]   # …then 60 bpm: not every other beat missing
    nums, _ = grid.number_beats(np.array(t))
    assert nums[-1] == 79
    tmap, _ = grid.tempo_map(np.array(t))
    assert [m["bpm"] for m in tmap] == [120.0, 60.0]


def test_double_triggers_are_dropped():
    t = np.sort(np.concatenate([np.arange(32) * 0.5, [4.02]]))
    nums, kept = grid.number_beats(t)
    assert len(kept) == 32 and nums[-1] == 31


def test_grid_without_map_uses_one_tempo():
    g = grid.Grid({"bpm": 120, "timeSignature": "3/4", "firstDownbeatSec": 1.0})
    assert g.sec(0) == 1.0 and g.bar_sec(2) == pytest.approx(2.5) and g.beat(0.0) == pytest.approx(-2)
    assert g.bar_sec(2, -1) == pytest.approx(2.0)          # one-beat pickup into bar 2


def test_grid_with_map_is_continuous_and_invertible():
    tmap = [{"beat": -2, "sec": 0.0, "bpm": 120}, {"beat": 8, "sec": 5.0, "bpm": 60}]
    g = grid.Grid({"bpm": 120, "timeSignature": "4/4", "map": tmap})
    assert g.sec(0) == 1.0 and g.sec(8) == 5.0 and g.sec(10) == 7.0
    for b in (-3, -2, 0, 7.5, 8, 12.25):
        assert g.beat(g.sec(b)) == pytest.approx(b)
    assert g.steps() == [(-2, 120), (8, 60)] and g.first_bpm == 120 and g.last_bpm == 60
    assert grid.main_bpm(tmap, end_beat=12) == 120     # 10 beats at 120, 4 at 60


def test_beats_on_grid_skips_off_beat_sounds():
    g = grid.Grid({"bpm": 120, "timeSignature": "4/4", "firstDownbeatSec": 1.0})
    beats, off = grid.beats_on_grid([0.5, 1.002, 1.5, 1.75, 3.0], g)
    assert beats == [-1, 0, 1, 4] and off == pytest.approx(2.0)
