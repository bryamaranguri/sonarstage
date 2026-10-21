"""Tempo, beats and bar phase from the click track.

Findings on real packs (Holy Forever, Alegras mis días):
- Clicks come as beat + eighth-note subdivision: two click sounds that differ in
  brightness and level. There is no separate bar accent, so the downbeat has to be
  found elsewhere (kick drum, guide cues).
"""
import numpy as np
from scipy.signal import butter, find_peaks, sosfilt


def detect_clicks(x, sr, min_gap=0.15):
    """Click onset times (s) plus per-click peak level (dB) and spectral brightness (Hz)."""
    mag = np.abs(x[:, 0]) if x.ndim == 2 else np.abs(x)
    hop = int(sr * 0.001)
    env = np.maximum.reduceat(mag, np.arange(0, len(mag), hop))
    # Leading zero: find_peaks ignores the edges, and many clicks start at sample 0
    padded = np.concatenate([[0.0], env])
    peaks, _ = find_peaks(padded, height=max(env.max() * 0.1, 1e-4), distance=int(min_gap / 0.001))
    peaks = peaks - 1
    mono = x[:, 0] if x.ndim == 2 else x
    times, levels, bright = [], [], []
    for p in peaks:
        a, b = max(0, (p - 10) * hop), (p + 1) * hop
        seg = mag[a:b]
        pk = seg.max()
        onset = a + int(np.argmax(seg > 0.2 * pk))
        times.append(onset / sr)
        levels.append(20 * np.log10(pk + 1e-12))
        w = mono[onset:onset + int(0.03 * sr)]
        if len(w) > 16:
            spec = np.abs(np.fft.rfft(w * np.hanning(len(w))))
            freqs = np.fft.rfftfreq(len(w), 1 / sr)
            bright.append(float((spec * freqs).sum() / (spec.sum() + 1e-12)))
        else:
            bright.append(0.0)
    return np.array(times), np.array(levels), np.array(bright)


def beats_from_clicks(times, bright):
    """Keep the brighter click class as beats when the click also plays subdivisions."""
    hi = bright > np.median(bright)
    alternating = len(times) > 8 and np.mean(hi[:-1] != hi[1:]) > 0.9
    return times[hi] if alternating else times


def tempo_summary(beats):
    """BPM, timing jitter (ms), tempo changes and long gaps (count-in pauses, stops)."""
    ioi = np.diff(beats)
    med = np.median(ioi)
    regular = ioi[(ioi > med * 0.75) & (ioi < med * 1.25)]
    bpm = 60 / regular.mean()
    changes = []
    if len(ioi) >= 8:
        rolling = np.convolve(ioi, np.ones(8) / 8, mode="valid")
        last = 60 / rolling[0]
        for i, r in enumerate(rolling):
            b = 60 / r
            if abs(b - last) > 1.0:
                changes.append({"time_s": round(float(beats[i]), 2), "bpm": round(float(b), 2)})
                last = b
    gaps = [
        {"time_s": round(float(beats[i]), 2), "length_s": round(float(d), 2)}
        for i, d in enumerate(ioi) if d > med * 1.5
    ]
    return {
        "bpm": round(float(bpm), 3),
        "jitter_ms": round(float(regular.std() * 1000), 2),
        "changes": changes,
        "gaps": gaps,
    }


def _low_energy_at(x, sr, times, cutoff=120, win=0.06):
    y = x.mean(axis=1) if x.ndim == 2 else x
    y = sosfilt(butter(4, cutoff, "low", fs=sr, output="sos"), y)
    n = int(win * sr)
    out = []
    for t in times:
        i = int(t * sr)
        out.append(np.sqrt(np.mean(y[i:i + n] ** 2)) if i + n < len(y) else 0.0)
    return np.array(out)


def bar_phase_from_kick(drums, sr, beats, candidates=(4, 3, 6)):
    """Beats per bar and downbeat phase from where the kick drum lands.

    Returns the best candidate and the normalised scores per phase, so the UI can show
    how confident the guess is. Holy Forever: 4/4 phase 0 with [1.0, 0.51, 0.45, 0.54].
    """
    kick = _low_energy_at(drums, sr, beats)
    result = {}
    for bpb in candidates:
        scores = np.array([kick[p::bpb].mean() for p in range(bpb)])
        scores = scores / (scores.max() + 1e-12)
        contrast = float(1 - np.sort(scores)[-2])          # gap between best and runner-up
        result[bpb] = {"phase": int(np.argmax(scores)), "scores": scores.round(2).tolist(), "contrast": round(contrast, 2)}
    best = max(result, key=lambda k: result[k]["contrast"])
    return best, result
