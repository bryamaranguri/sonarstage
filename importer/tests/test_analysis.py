"""Synthetic-audio checks for the analysis modules (no real packs needed)."""
import numpy as np

from sonarstage_import import align, guide, tempo

SR = 44100


def click_track(bpm=120, seconds=20, subdivisions=True):
    """Beat clicks (bright, loud) and optional eighth-note clicks (dull, soft)."""
    x = np.zeros(int(SR * seconds), dtype=np.float32)
    beat = 60 / bpm
    t = np.arange(int(0.01 * SR)) / SR
    bright = (np.sin(2 * np.pi * 3000 * t) * np.exp(-t * 400)).astype(np.float32)
    dull = (0.5 * np.sin(2 * np.pi * 1500 * t) * np.exp(-t * 400)).astype(np.float32)
    k = 0.0
    while k < seconds - 0.1:
        i = int(k * SR)
        x[i:i + len(bright)] += bright
        if subdivisions:
            j = int((k + beat / 2) * SR)
            if j + len(dull) < len(x):
                x[j:j + len(dull)] += dull
        k += beat
    return np.stack([x, x], axis=1)


def test_eighth_note_click_reads_true_tempo():
    x = click_track(bpm=72)
    times, _, bright = tempo.detect_clicks(x, SR)
    beats = tempo.beats_from_clicks(times, bright)
    assert len(beats) < len(times)
    assert abs(tempo.tempo_summary(beats)["bpm"] - 72) < 0.1


def test_click_at_sample_zero_is_detected():
    times, _, bright = tempo.detect_clicks(click_track(bpm=120), SR)
    assert times[0] < 0.002


def test_quarter_note_click_is_kept():
    x = click_track(bpm=128, subdivisions=False)
    times, _, bright = tempo.detect_clicks(x, SR)
    beats = tempo.beats_from_clicks(times, bright)
    assert abs(tempo.tempo_summary(beats)["bpm"] - 128) < 0.1


def test_lag_of_delayed_copy():
    x = click_track(bpm=100)
    delayed = np.roll(x, int(0.040 * SR), axis=0)
    lag, sharp = align.lag_ms(align.onset_envelope(x, SR), align.onset_envelope(delayed, SR))
    assert lag == 40
    assert align.classify(lag, sharp) == "desfasado"
    assert align.classify(5, sharp) == "ok"
    assert align.classify(5, 1.0) == "no_medible"


def test_bar_position_snaps_onset_just_before_downbeat():
    beats = np.arange(0, 40, 0.5)            # 120 BPM
    assert guide.bar_position(2.0, beats) == (2, 1.0)
    assert guide.bar_position(1.995, beats) == (2, 1.0)
    bar, beat = guide.bar_position(2.5, beats)
    assert (bar, round(beat)) == (2, 2)
