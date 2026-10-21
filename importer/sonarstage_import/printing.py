"""Gain planning and printing of prepared stems.

Design notes:
- Stems from a multitrack pack are already balanced by whoever made it: summed at 0 dB
  they rebuild the original mix. So the default is to keep that balance and move the
  whole song with one gain. A per-role template (dB offsets) is optional, for users who
  always want e.g. the pad a bit lower.
- The song gain aims at a common loudness for the full mix (all stems, including the
  ones the band plays live, so unmuting a backup keeps the balance), but never lets the
  summed mix peak above PEAK_CEILING: no limiter, because limiting stems separately
  would change the mix and limiting the sum is not possible once they are separate.
- Click and guide are set to fixed levels of their own, whatever the source.
"""
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

# Common loudness of the full mix. -18 rather than -16: with typical packs the -1 dBFS
# peak ceiling already pulls songs to -17/-18, and then the peak, not the loudness,
# would decide the level (measured on two real packs).
TARGET_LUFS = -18.0
PEAK_CEILING_DBFS = -1.0       # headroom for the summed mix at the interface output
STEM_CEILING_DBFS = -0.3       # no single printed stem may clip a 24-bit file
# A click is all peak and little energy: with a -0.3 dBFS ceiling it lands around
# -23 LUFS (measured on two packs), so that is its realistic common level.
CUE_TARGETS_LUFS = {"click": -23.0, "guide": -18.0}
CUE_ROLES = set(CUE_TARGETS_LUFS)


def db_to_gain(db):
    return 10 ** (db / 20)


def peak_db(x):
    return float(20 * np.log10(np.abs(x).max() + 1e-12))


def plan_song_gain(mix_lufs, mix_peak_db, stem_peaks_db, target_lufs=TARGET_LUFS):
    """One gain for every music stem. Returns (gain_db, limited_by)."""
    candidates = {
        "volumen objetivo": target_lufs - mix_lufs,
        "pico de la mezcla": PEAK_CEILING_DBFS - mix_peak_db,
    }
    if stem_peaks_db:
        candidates["pico de un stem"] = STEM_CEILING_DBFS - max(stem_peaks_db)
    reason = min(candidates, key=candidates.get)
    return round(candidates[reason], 2), reason


def plan_cue_gain(role, stem_lufs, stem_peak_db):
    target = CUE_TARGETS_LUFS[role]
    return round(min(target - stem_lufs, STEM_CEILING_DBFS - stem_peak_db), 2)


def measure_mix(stems, sr, offsets_db=None):
    """Loudness and peak of the sum of `stems` (iterable of (role, array)), with optional
    per-role offsets. Streams: only the running sum is kept in memory."""
    offsets_db = offsets_db or {}
    mix, stem_peaks = None, []
    for role, x in stems:
        g = db_to_gain(offsets_db.get(role, 0.0))
        y = x * g
        stem_peaks.append(peak_db(y))
        if mix is None:
            mix = y.astype(np.float64)
        else:
            n = min(len(mix), len(y))
            mix = mix[:n] + y[:n]
    if mix is None:
        return None
    return {
        "lufs": float(pyln.Meter(sr).integrated_loudness(mix)),
        "peak_db": peak_db(mix),
        "stem_peaks_db": stem_peaks,
    }


def write_stem(path, x, sr, gain_db, fmt="FLAC"):
    """Write x * gain as 24-bit FLAC (library) or WAV (show)."""
    y = (x * db_to_gain(gain_db)).astype(np.float32)
    sf.write(str(path), y, sr, subtype="PCM_24", format=fmt)
    return peak_db(y)
