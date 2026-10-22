"""Section names from guide words (the Whisper part is replaced by word lists)."""
import pytest

from sonarstage_import.label import name_from_words, propose


@pytest.mark.parametrize("heard,expected", [
    ("Intro", ("Intro", "intro")),
    ("Verse one", ("Verso 1", "verse")),
    ("verse 2", ("Verso 2", "verse")),
    ("Pre-chorus", ("Pre coro", "prechorus")),
    ("Chorus two three four", ("Coro", "chorus")),       # the count after the name is not a number
    ("Chorus 2", ("Coro 2", "chorus")),
    ("Coro", ("Coro", "chorus")),
    ("Puente", ("Puente", "bridge")),
    ("Bridge", ("Puente", "bridge")),
    ("Instrumental", ("Instrumental", "interlude")),
    ("Turnaround", ("Interludio", "interlude")),
    ("Tag", ("Tag", "tag")),
    ("Ending", ("Final", "outro")),
    ("Breakdown", ("Break", "other")),
    ("Verso dos", ("Verso 2", "verse")),
    ("Estrofa", ("Verso", "verse")),
    ("Exhortación", ("Exhortación", "other")),
    ("one two three four", None),                         # just counting
    ("", None),
])
def test_name_from_words(heard, expected):
    assert name_from_words(heard) == expected


def song(sections):
    return {"tempo": {"bpm": 120, "timeSignature": "4/4", "firstDownbeatSec": 0.0},
            "sections": [{"name": n, "kind": "other", "startBar": b, "bars": 4} for n, b in sections]}


def test_words_are_assigned_to_the_announcement_before_each_section():
    s = song([("Cuenta", 1), ("Sección 1", 3), ("Sección 2", 7), ("Sección 3", 11)])
    # 2 s per bar: bar 2 starts at 2 s, bar 6 at 10 s, bar 10 at 18 s
    words = [(0.0, 0.3, "One"), (1.0, 1.3, "two"), (2.1, 2.6, "Intro"),
             (10.1, 10.6, "Verse"), (10.7, 11.0, "one"),
             (18.2, 18.9, "Chorus")]
    p = propose(s, words)
    assert [(x["name"], x["kind"]) for x in p] == [("Cuenta", "other"), ("Intro", "intro"),
                                                  ("Verso 1", "verse"), ("Coro", "chorus")]


def test_unrecognised_announcement_keeps_the_provisional_name():
    s = song([("Cuenta", 1), ("Sección 1", 3)])
    p = propose(s, [(2.1, 2.5, "hmm")])
    assert p[1]["name"] == "Sección 1" and p[1]["matched"] is False
