"""Loudness, peak, activity and mono compatibility per stem and for the full mix."""
import numpy as np
import pyloudnorm as pyln


def stem_levels(x, sr):
    meter = pyln.Meter(sr)
    active = np.abs(x).max(axis=1) > 10 ** (-60 / 20)
    per_second = np.array([active[i:i + sr].any() for i in range(0, len(active), sr)])
    has_signal = bool(per_second.any())
    lufs = meter.integrated_loudness(x) if has_signal else float("-inf")
    mono = np.repeat(x.mean(axis=1, keepdims=True), 2, axis=1)
    lufs_mono = meter.integrated_loudness(mono) if has_signal else float("-inf")
    left, right = x[:, 0], x[:, 1]
    corr = float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right) + 1e-12))
    loss = float(lufs - lufs_mono) if has_signal else 0.0
    return {
        "lufs": round(float(lufs), 1),
        "peak_dbfs": round(float(20 * np.log10(np.abs(x).max() + 1e-12)), 1),
        "active_pct": int(round(100 * per_second.mean())),
        "lr_correlation": round(corr, 2),
        "mono_loss_db": round(loss, 1),
        # ~3 dB loss is normal for a wide, uncorrelated stem; negative correlation means
        # parts cancel when summed to mono (the 2-output profile)
        "mono_safe": not (corr < -0.2 or loss > 4.5),
    }


def mix_levels(stems, sr):
    """Sum of stems (equal-length float arrays) and its loudness."""
    n = min(len(s) for s in stems)
    mix = np.sum([s[:n] for s in stems], axis=0)
    return {
        "lufs": round(float(pyln.Meter(sr).integrated_loudness(mix)), 1),
        "peak_dbfs": round(float(20 * np.log10(np.abs(mix).max() + 1e-12)), 1),
    }
