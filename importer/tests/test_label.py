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


def test_unnamed_section_after_the_count_is_the_intro():
    s = song([("Cuenta", 1), ("Sección 1", 3), ("Sección 2", 7)])
    words = [(0.0, 0.3, "One"), (1.0, 1.3, "two"), (2.1, 2.4, "three"), (10.1, 10.6, "Verse")]
    p = propose(s, words)
    assert (p[1]["name"], p[1]["kind"], p[1]["how"]) == ("Intro", "intro", "after-count")
    assert p[2]["name"] == "Verso"


def test_dynamics_cue_continues_the_previous_section():
    s = song([("Cuenta", 1), ("Sección 1", 3), ("Sección 2", 7), ("Sección 3", 9)])
    # "coro, baja la intensidad" before bar 7, then "toda la banda" before bar 9
    words = [(2.1, 2.5, "Intro"), (10.1, 10.5, "coro"), (10.6, 11.0, "baja"),
             (14.1, 14.5, "toda"), (14.6, 14.9, "la"), (15.0, 15.3, "banda")]
    p = propose(s, words)
    assert [(x["name"], x["how"]) for x in p[1:]] == [("Intro", "guide"), ("Coro", "guide"),
                                                     ("Coro", "continues")]


def test_apply_keeps_guide_text_only_when_something_was_heard(tmp_path):
    from sonarstage_import.label import apply
    s = song([("Cuenta", 1), ("Sección 1", 3), ("Sección 2", 7)])
    p = propose(s, [(10.1, 10.5, "Chorus")])
    apply(tmp_path / "cancion.json", s, p)
    assert [x["name"] for x in s["sections"]] == ["Cuenta", "Intro", "Coro"]
    assert "guide" not in s["sections"][1] and s["sections"][2]["guide"] == "Chorus"
