import pytest

from sonarstage_import.roles import classify

# File names exactly as they arrived in real packs
CASES = {
    "Click Track.m4A": "click", "Click.mp3": "click",
    "Guide.m4A": "guide", "Cues.mp3": "guide",
    "Drums.m4A": "drums", "Aux Drums.mp3": "perc", "Perc.m4A": "perc", "Loop.mp3": "perc",
    "Bass.m4A": "bass", "Synth Bass.mp3": "bass",
    "EG 1.m4A": "eg", "EG 3.mp3": "eg", "AG.mp3": "ag",
    "Keys 1.m4A": "keys", "Wurli.mp3": "keys", "Piano.m4A": "piano", "Organ.wav": "organ",
    "Strings.mp3": "strings",
    "BGVS.m4A": "choir", "BGVS 2.m4A": "choir", "Oohs.mp3": "choir", "Choir.wav": "choir",
    "Vox Chop.m4A": "fx", "FX.m4A": "fx",
    "Secuencia.wav": "premix", "Vocals.wav": "leadVocal",
    "Guitarra Eléctrica.wav": "eg", "Batería.wav": "drums", "Guía.wav": "guide",
}


@pytest.mark.parametrize("name,role", CASES.items())
def test_classify(name, role):
    assert classify(name)[0] == role


def test_click_and_guide_are_not_transposed():
    assert classify("Click.mp3")[2] is False
    assert classify("Cues.mp3")[2] is False
    assert classify("Keys 1.m4A")[2] is True


def test_unknown_name_is_extra():
    assert classify("Thing 7.wav")[0] == "extra"
