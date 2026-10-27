"""Key names, transposition and the estimate from a pitch-class profile."""
import numpy as np
import pytest

from sonarstage_import import musickey as mk

SR = mk.SR


def test_names_and_spelling():
    assert mk.parse("G") == (7, False) and mk.parse("F#m") == (6, True) and mk.parse("Bb") == (10, False)
    assert mk.normalize("A#") == "Bb" and mk.normalize("Gb") == "F#" and mk.normalize("?") is None
    with pytest.raises(mk.KeyError_):
        mk.parse("H")
    with pytest.raises(mk.KeyError_):
        mk.parse("Gsus")


def test_transpose():
    assert mk.transpose("G", 2) == "A" and mk.transpose("F#m", 1) == "Gm" and mk.transpose("C", -1) == "B"
    assert mk.transpose("Bb", -1) == "A" and mk.transpose("?", 3) is None


def _chord_tones(freqs, seconds=6):
    t = np.arange(int(SR * seconds)) / SR
    return sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)


def _progression(roots_semis, base=196.0, minor=False):
    """A I–IV–V–I style progression on triads, each chord a few seconds."""
    parts = []
    for r in roots_semis:
        f = base * 2 ** (r / 12)
        third = 3 if minor and r == 0 else 4
        parts.append(_chord_tones([f, f * 2 ** (third / 12), f * 2 ** (7 / 12), f / 2]))
    return np.concatenate(parts)


def test_estimates_a_major_progression():
    x = _progression([0, 5, 7, 0, 5, 7, 0])                 # G C D G …
    est = mk.estimate([("keys", "g.wav")], decode=lambda p, sr, mono: x[:, None])
    assert est["key"] == "G" and est["confidence"] > 0


def test_ignores_drums_click_and_vocals():
    est = mk.estimate([("drums", "d"), ("click", "c"), ("leadVocal", "v")], decode=lambda *a, **k: 1 / 0)
    assert est is None
