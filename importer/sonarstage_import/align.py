"""Stem alignment against the click.

Global cross-correlation of onset envelopes. Only stems with clear transients (drums,
loops, rhythmic keys) give a sharp correlation peak; pads, strings or sustained
guitars do not, and their measured lag must not be used to shift them.
"""
import numpy as np

SHARPNESS_MIN = 3.3   # below this the lag is noise (calibrated on two real packs)
# Offsets within this are musical feel or measurement noise, not a misalignment.
# Real packs measured 0–11 ms; an encoder-delay problem shows up as 25–60 ms.
TOLERANCE_MS = 15


def onset_envelope(x, sr, hop_s=0.001):
    y = x.mean(axis=1) if x.ndim == 2 else x
    h = int(hop_s * sr)
    n = len(y) // h
    e = np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(axis=1))
    d = np.maximum(np.diff(np.log(e + 1e-5), prepend=0), 0)
    d[e < 1e-4] = 0
    return d - d.mean()


def lag_ms(ref_env, env, max_ms=100):
    """Lag of env relative to ref_env in ms (positive = late) and peak sharpness."""
    n = min(len(ref_env), len(env))
    a, b = ref_env[:n], env[:n]
    size = 1 << int(np.ceil(np.log2(2 * n)))
    xc = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    window = np.concatenate([xc[-max_ms:], xc[:max_ms + 1]])
    k = int(np.argmax(window)) - max_ms
    sharp = (window.max() - np.median(window)) / (window.std() + 1e-12)
    return -k, float(sharp)


def classify(lag, sharpness):
    if sharpness < SHARPNESS_MIN:
        return "no_medible"
    return "ok" if abs(lag) <= TOLERANCE_MS else "desfasado"
