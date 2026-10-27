"""Tempo map: where every beat of a song falls in its audio.

Clips play unwarped (the audio is never stretched on stage), so Live's grid has to
follow the audio instead: the show's tempo automation is written from this map, and the
click, locators, MIDI changes and voice-command jumps all land on the beats the band
hears. One tempo per song only works while the song never changes tempo.

The map comes from the click: every detected beat gets a number (a stop counts as the
beats it leaves silent), and the numbered beats are fitted with as few constant-tempo
segments as keep every beat within TOLERANCE_S of the grid. A song in constant tempo is
one segment; a ritardando becomes short steps.

Beats are counted from beat 1 of bar 1 (beat 0); pickups before it are negative. In
cancion.json, tempo.map = [{"beat", "sec", "bpm"}, ...]: each segment runs until the next
one, the first also covers the file before it and the last runs to the end of the file.
An empty map means one tempo (`bpm`) from `firstDownbeatSec` (songs imported before).
"""
import math

import numpy as np

TOLERANCE_S = 0.005              # inaudible against a click; detection jitter on real packs is ~1 ms
MIN_BPM, MAX_BPM = 30.0, 300.0   # what a stop may become (Live itself accepts 20-999)
NICE_STEPS = (1.0, 0.5, 0.1, 0.01)


def number_beats(times):
    """Beat number of each click beat, and the beats kept.

    A long interval counts as several beats only when it is isolated: if the intervals
    after it are as long, the tempo dropped (a playing click never skips beats). Clicks
    closer than 40 % of a beat are double triggers and are dropped.
    """
    times = np.asarray(times, float)
    if len(times) < 2:
        return np.arange(len(times)), times
    ioi = np.diff(times)
    period = float(np.median(ioi[:16]))
    nums, kept, periods = [0], [times[0]], []
    for i in range(1, len(times)):
        d = times[i] - kept[-1]
        if d < 0.4 * period:
            continue
        steps = max(1, round(d / period))
        if steps > 1:
            after = ioi[i:i + 3]
            if len(after) and np.all(np.abs(after - d) < 0.15 * d):
                steps = 1
            else:
                steps = min(max(steps, math.ceil(d * MIN_BPM / 60)), max(1, math.floor(d * MAX_BPM / 60)))
        nums.append(nums[-1] + steps)
        kept.append(times[i])
        periods.append(d / steps)
        period = float(np.median(periods[-8:]))
    return np.array(nums), np.array(kept)


def _nice(bpm, dk, dt, tol):
    """The roundest tempo that still keeps the segment's beats within tolerance."""
    for step in NICE_STEPS:
        c = round(bpm / step) * step
        if c > 0 and np.max(np.abs(dt - dk * 60 / c)) <= tol:
            return round(c, 2)
    return round(bpm, 4)


def fit_segments(nums, times, tol=TOLERANCE_S):
    """[(beat_number, sec, bpm)]: a continuous, piecewise-constant tempo through the beats.

    Greedy: each segment starts where the previous one ended and grows while every beat
    it covers stays within `tol` of where the segment puts it.
    """
    k, t = np.asarray(nums, float), np.asarray(times, float)
    if len(k) < 2:
        raise ValueError("Hacen falta al menos dos golpes de click.")
    segs, i0, t0 = [], 0, float(t[0])
    while i0 < len(k) - 1:
        best = None
        for j in range(i0 + 1, len(k)):
            if not segs:
                # the first segment has no previous end to start from: fit its start too,
                # so the first beat's own jitter does not tilt the whole song
                dk, tt = k[i0:j + 1] - k[i0], t[i0:j + 1]
                p, start = (np.polyfit(dk, tt, 1) if j > i0 + 1 else (tt[1] - tt[0], tt[0]))
                p, start = float(p), float(start)
                ok = np.max(np.abs(tt - start - dk * p)) <= tol
            else:
                dk, dt = k[i0 + 1:j + 1] - k[i0], t[i0 + 1:j + 1] - t0
                p = float((dk * dt).sum() / (dk * dk).sum())      # seconds per beat through (k0, t0)
                start = t0
                ok = np.max(np.abs(dt - dk * p)) <= tol
            if best is not None and not ok:
                break
            best = (j, p, start)
        j, p, t0 = best
        bpm = _nice(60 / p, k[i0 + 1:j + 1] - k[i0], t[i0 + 1:j + 1] - t0, tol)
        segs.append((int(k[i0]), float(t0), bpm))
        t0 += (k[j] - k[i0]) * 60 / bpm
        i0 = j
    # a segment that ends only because of one jittery beat continues at the same tempo
    return [s for n, s in enumerate(segs) if n == 0 or s[2] != segs[n - 1][2]]


def tempo_map(beats, downbeat=0, tol=TOLERANCE_S):
    """Map for cancion.json from the click beats; `downbeat` = index of beat 1 of bar 1.

    Returns (map, stats) with the largest distance between a click beat and the grid.
    """
    nums, kept = number_beats(beats)
    i = int(np.argmin(np.abs(kept - beats[downbeat])))
    kd = int(nums[i])
    segs = fit_segments(nums, kept, tol)
    tmap = [{"beat": k - kd, "sec": round(s, 4), "bpm": bpm} for k, s, bpm in segs]
    grid = Grid({"bpm": tmap[0]["bpm"], "timeSignature": "4/4", "map": tmap})
    err = np.abs(np.array([grid.sec(n - kd) for n in nums]) - kept)
    return tmap, {"segments": len(tmap), "max_error_ms": round(float(err.max()) * 1000, 2),
                  "silent_beats": int(nums[-1] + 1 - len(nums))}


def main_bpm(tmap, end_beat=None):
    """The tempo that covers the most beats (what a song is "in")."""
    if not tmap:
        return None
    spans = {}
    ends = [m["beat"] for m in tmap[1:]] + [end_beat if end_beat is not None else tmap[-1]["beat"] + 1]
    for m, end in zip(tmap, ends):
        spans[m["bpm"]] = spans.get(m["bpm"], 0) + max(0, end - m["beat"])
    return max(spans, key=spans.get)


class Grid:
    """Beat <-> second conversion for one song (seconds in its audio files)."""

    def __init__(self, tempo):
        tmap = tempo.get("map") or []
        if tmap:
            self.segs = [(float(m["beat"]), float(m["sec"]), float(m["bpm"])) for m in tmap]
        else:
            self.segs = [(0.0, float(tempo.get("firstDownbeatSec", 0.0)), float(tempo["bpm"]))]
        self.bpb = int(tempo.get("timeSignature", "4/4").split("/")[0])

    def _seg(self, value, col):
        i = 0
        for n, s in enumerate(self.segs):
            if s[col] <= value + 1e-9:
                i = n
        return self.segs[i]

    def sec(self, beat):
        b, s, bpm = self._seg(beat, 0)
        return s + (beat - b) * 60 / bpm

    def beat(self, sec):
        b, s, bpm = self._seg(sec, 1)
        return b + (sec - s) * bpm / 60

    def bar_sec(self, bar, beats=0.0):
        """Second of bar `bar` (1-based), plus `beats` (negative for a pickup)."""
        return self.sec((bar - 1) * self.bpb + beats)

    def steps(self):
        """[(beat, bpm)] where the tempo changes, starting with the first segment."""
        return [(b, bpm) for b, _, bpm in self.segs]

    @property
    def first_bpm(self):
        return self.segs[0][2]

    @property
    def last_bpm(self):
        return self.segs[-1][2]


def beats_on_grid(times, g, max_off=0.25):
    """Which grid beats (from bar 1) a click plays, and how far it is from the grid.

    times: click beats in seconds (tempo.beats_from_clicks). A sound more than `max_off`
    of a beat away from any grid beat is not a beat (left out). Returns (sorted beat
    numbers, largest distance in ms between a click beat and its grid beat)."""
    beats, worst = set(), 0.0
    for t in times:
        b = g.beat(float(t))
        n = round(b)
        if abs(b - n) <= max_off:
            beats.add(int(n))
            worst = max(worst, abs(float(t) - g.sec(n)))
    return sorted(beats), round(worst * 1000, 2)
