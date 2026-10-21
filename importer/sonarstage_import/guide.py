"""Where the guide speaks, placed on the bar grid.

Labels ("coro", "verso 2"…) need speech recognition (Whisper), which runs on the user's
Mac with a bundled model. Without it we still get the cue positions, which already
outline the song form: on real packs the main cues fall on beat 1 every 4 or 8 bars.
"""
import numpy as np


def speech_segments(x, sr, hop=0.01, rel_db=-35, min_gap=0.25, min_dur=0.12):
    y = x.mean(axis=1) if x.ndim == 2 else x
    h = int(hop * sr)
    n = len(y) // h
    e = 20 * np.log10(np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9)
    on = e > (e.max() + rel_db)
    segs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        if not v and start is not None:
            segs.append([start * hop, i * hop])
            start = None
    if start is not None:
        segs.append([start * hop, n * hop])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [(a, b) for a, b in merged if b - a >= min_dur]


def bar_position(t, beats, beats_per_bar=4, phase=0, snap_beats=0.05):
    """1-based (bar, beat) of time t on the beat grid. Onsets a hair before a beat snap to it."""
    period = float(np.median(np.diff(beats)))
    i = int(np.searchsorted(beats, t + snap_beats * period) - 1)
    i = max(i, 0)
    frac = max(0.0, (t - beats[i]) / period)
    k = i - phase
    return k // beats_per_bar + 1, round(k % beats_per_bar + 1 + frac, 2)


def guide_cues(guide, sr, beats, beats_per_bar=4, phase=0):
    cues = []
    for a, b in speech_segments(guide, sr):
        bar, beat = bar_position(a, beats, beats_per_bar, phase)
        cues.append({"time_s": round(a, 2), "duration_s": round(b - a, 2), "bar": int(bar), "beat": beat})
    return cues
