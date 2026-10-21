"""Analyse an extracted stem pack and print a report.

    python -m sonarstage_import.analyze <pack folder> [--json out.json] [--target-lufs -18]

Prototype for phase 1. Reads only; never modifies the pack.
"""
import argparse
import json
import sys
from pathlib import Path

from . import align, guide, levels, roles, tempo
from .audio_io import decode, probe

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg"}
SR = 44100


def analyze(pack, target_lufs=-18.0):
    files = sorted(p for p in Path(pack).iterdir() if p.suffix.lower() in AUDIO_EXT)
    stems = []
    for f in files:
        role, label, harmonic = roles.classify(f.name)
        stems.append({"file": f.name, "role": role, "label": label, "harmonic": harmonic, **probe(f)})

    by_role = {}
    for s in stems:
        by_role.setdefault(s["role"], []).append(s)
    report = {"pack": Path(pack).name, "stems": stems, "warnings": []}
    if "click" not in by_role:
        report["warnings"].append("No se encontró pista de click: tempo y compases quedan para revisión manual.")
        return report

    click = decode(Path(pack) / by_role["click"][0]["file"], SR)
    times, lv, br = tempo.detect_clicks(click, SR)
    beats = tempo.beats_from_clicks(times, br)
    report["tempo"] = {**tempo.tempo_summary(beats), "first_beat_s": round(float(beats[0]), 3),
                       "click_subdivisions": bool(len(beats) < len(times))}

    bpb, phase = 4, 0
    if "drums" in by_role:
        bpb, meters = tempo.bar_phase_from_kick(decode(Path(pack) / by_role["drums"][0]["file"], SR), SR, beats)
        phase = meters[bpb]["phase"]
        report["meter"] = {"beats_per_bar": bpb, "downbeat_phase": phase, "candidates": meters}
    else:
        report["warnings"].append("Sin batería: se asume 4/4 desde el primer golpe del click.")

    # One stem in memory at a time: a 5-minute stereo stem is ~110 MB as float32,
    # and a pack can have 20 of them (the MacBook Air has 8 GB in total).
    ref_env = align.onset_envelope(click, SR)
    mix, guide_audio = None, None
    for s in stems:
        x = decode(Path(pack) / s["file"], SR)
        if s["role"] == "guide" and guide_audio is None:
            guide_audio = x
        elif s["role"] != "click":
            if mix is None:
                mix = x.copy()
            else:
                n = min(len(mix), len(x))
                mix = mix[:n]
                mix += x[:n]
        lag, sharp = align.lag_ms(ref_env, align.onset_envelope(x, SR))
        s["alignment"] = {"lag_ms": lag, "sharpness": round(sharp, 1), "status": align.classify(lag, sharp)}
        s["levels"] = levels.stem_levels(x, SR)
        if not s["levels"]["mono_safe"]:
            report["warnings"].append(f"{s['label']}: pierde contenido al sumarse a mono.")
        if s["alignment"]["status"] == "desfasado":
            report["warnings"].append(f"{s['label']}: desfase de {lag} ms respecto al click.")

        del x

    if mix is not None:
        m = levels.mix_levels([mix], SR)
        m["suggested_gain_db"] = round(target_lufs - m["lufs"], 1)
        m["target_lufs"] = target_lufs
        report["mix"] = m
        if m["peak_dbfs"] > 0:
            report["warnings"].append(f"La suma de stems pasa de 0 dBFS (pico {m['peak_dbfs']} dB): se corrige al normalizar.")

    if guide_audio is not None:
        report["guide_cues"] = guide.guide_cues(guide_audio, SR, beats, bpb, phase)
    return report


def print_summary(r):
    print(f"\n{r['pack']}")
    print("-" * len(r["pack"]))
    if "tempo" in r:
        t = r["tempo"]
        meter = r.get("meter", {})
        print(f"Tempo: {t['bpm']} BPM (variación {t['jitter_ms']} ms)"
              f"{' · click en corcheas' if t['click_subdivisions'] else ''}"
              f" · compás {meter.get('beats_per_bar', 4)}/4"
              f"{' · cambios: ' + str(t['changes']) if t['changes'] else ''}")
    print(f"\n{'Stem':16} {'Rol':10} {'Formato':12} {'LUFS':>6} {'Activo':>6}  Alineación")
    for s in r["stems"]:
        fmt = f"{s['codec']} {s['bitrate_kbps'] or ''}".strip()
        a, lv = s.get("alignment", {}), s.get("levels", {})
        al = {"ok": f"ok ({a.get('lag_ms'):+d} ms)", "desfasado": f"DESFASE {a.get('lag_ms'):+d} ms",
              "no_medible": "sin transientes"}.get(a.get("status"), "")
        print(f"{s['label'][:16]:16} {s['role']:10} {fmt:12} {lv.get('lufs', ''):>6} {str(lv.get('active_pct', '')) + '%':>6}  {al}")
    if "mix" in r:
        m = r["mix"]
        print(f"\nMezcla completa: {m['lufs']} LUFS, pico {m['peak_dbfs']} dBFS → ganancia para {m['target_lufs']} LUFS: {m['suggested_gain_db']:+} dB")
    if r.get("guide_cues"):
        bars = [c["bar"] for c in r["guide_cues"] if c["beat"] < 1.5]
        print(f"Guía: {len(r['guide_cues'])} avisos; en tiempo 1 en los compases {bars}")
    for w in r["warnings"]:
        print(f"⚠ {w}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack")
    ap.add_argument("--json")
    ap.add_argument("--target-lufs", type=float, default=-18.0)
    args = ap.parse_args(argv)
    report = analyze(args.pack, args.target_lufs)
    print_summary(report)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
