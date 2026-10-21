"""Stem role from the file name (Spanish and English names seen in real packs).

Order matters: more specific patterns go first ("click track" before "track",
"synth bass" before "synth", "aux drums" before "drums", "vox chop" before "vox").
"""
import re
import unicodedata

RULES = [
    ("click", r"click|clic|metr[oó]nomo|metronome"),
    ("guide", r"gu[ií]a|guide|cues?\b|voice ?guide"),
    ("fx", r"vox ?chop|\bfx\b|efectos?|riser|sweep|impact"),
    ("perc", r"aux ?drums|perc|loop|shaker|tamb|conga|cajon|caj[oó]n"),
    ("drums", r"drums?|bater[ií]a|\bkit\b"),
    ("bass", r"synth ?bass|bass|bajo"),
    ("eg", r"\beg\b|e\.? ?gtr|electric|el[eé]ctrica"),
    ("ag", r"\bag\b|acoustic|ac[uú]stica"),
    ("organ", r"organ|[oó]rgano|\bb3\b|hammond"),
    ("piano", r"piano"),
    ("keys", r"keys?|teclado|wurli|rhodes|\bep\b"),
    ("pad", r"pads?\b"),
    ("synth", r"synth|sinte"),
    ("strings", r"strings?|cuerdas|violin|cello"),
    ("choir", r"bgvs?|coros?|choir|oohs?|aahs?|background|backing ?vox"),
    ("leadVocal", r"lead|vocals?|\bvox\b|\bvoz\b|voces"),
    ("premix", r"secuencia|full ?mix|playback|\btracks?\b|\bmix\b"),
]

HARMONIC = {"bass", "eg", "ag", "keys", "piano", "organ", "synth", "pad", "strings",
            "leadVocal", "choir", "fx", "premix"}


def _normalise(name):
    stem = name.rsplit(".", 1)[0]
    stem = unicodedata.normalize("NFC", stem).lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", stem).strip()


def classify(filename):
    """(role, label, harmonic). Unknown names become role 'extra' for the user to confirm."""
    norm = _normalise(filename)
    label = filename.rsplit(".", 1)[0].strip()
    for role, pattern in RULES:
        if re.search(pattern, norm):
            return role, label, role in HARMONIC
    return "extra", label, True
