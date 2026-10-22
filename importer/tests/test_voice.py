"""Voice control: phrases -> commands, utterance cutting, and the loop (Whisper faked)."""
import numpy as np
import pytest

from sonarstage_import.voice import Context, Segmenter, listen
from sonarstage_import.voice_commands import parse

SECTIONS = ["Intro", "Verso 1", "Pre coro", "Coro 1", "Verso 2", "Coro 2", "Instrumental", "Puente", "Final"]
TRACKS = ["Click", "Guía", "Batería", "Bajo", "Guitarra eléctrica", "Secuencia"]
SONGS = [(1, "Holy Forever"), (2, "Alegras mis días")]


@pytest.mark.parametrize("said,commands", [
    ("Secuencia, repetimos el coro.", [{"cmd": "repeat"}]),                 # we are in the chorus
    ("Secuencia, otra vez", [{"cmd": "repeat"}]),
    ("Secuencia, en bucle", [{"cmd": "hold"}]),
    ("Secuencia, mantenemos el coro", [{"cmd": "hold"}]),
    ("Secuencia, una vez más", [{"cmd": "repeat"}]),
    ("Secuencia, repetimos el puente", [{"cmd": "goto", "section": "Puente"}]),   # elsewhere: go there
    ("Secuencia, vamos al puente", [{"cmd": "goto", "section": "Puente"}]),
    ("Secuencia, al verso dos", [{"cmd": "goto", "section": "Verso 2"}]),
    ("Secuencia, vamos al verso", [{"cmd": "goto", "section": "Verso"}]),   # the bridge picks the next one
    ("Secuencias, vamos al pre-coro", [{"cmd": "goto", "section": "Pre coro"}]),
    ("Secuencia, chorus", [{"cmd": "goto", "section": "Coro"}]),
    ("Secuencia, ¡Perso!", [{"cmd": "goto", "section": "Verso"}]),          # Whisper's take on "Verso"
    ("Secuencia, instrumentar", [{"cmd": "goto", "section": "Instrumental"}]),
    ("Secuencia, empezamos desde el coro", [{"cmd": "goto", "section": "Coro"}, {"cmd": "play"}]),
    ("Secuencia, siguiente", [{"cmd": "next_section"}]),
    ("Secuencia, seguimos", [{"cmd": "release"}]),
    ("Secuencia, cancela", [{"cmd": "cancel"}]),
    ("Secuencia, para", [{"cmd": "stop"}]),
    ("Secuencia, dale", [{"cmd": "play"}]),
    ("Secuencia, siguiente canción", [{"cmd": "next_song"}]),
    ("Secuencia, canción tres", [{"cmd": "song", "number": 3}]),
    ("Secuencia, Alegras mis días", [{"cmd": "song", "number": 2}]),
    ("Secuencia, silencia la guitarra", [{"cmd": "mute", "track": "Guitarra eléctrica", "on": True}]),
    ("Secuencia, activa el bajo", [{"cmd": "mute", "track": "Bajo", "on": False}]),
    ("Secuencia, quita la guía", [{"cmd": "mute", "track": "Guía", "on": True}]),
    ("Secuencia. Desactivar la batería.", [{"cmd": "mute", "track": "Batería", "on": True}]),   # was read as "activar"
    ("Secuencia desactivar batería", [{"cmd": "mute", "track": "Batería", "on": True}]),
    ("secuencia, motear batería.", [{"cmd": "mute", "track": "Batería", "on": True}]),
    ("Secuencia, Dali.", [{"cmd": "play"}]),
    ("banda vamos al coro secuencia vamos al coro", [{"cmd": "goto", "section": "Coro"}]),
    ("Sequencia, silencio la batería.", [{"cmd": "mute", "track": "Batería", "on": True}]),
    ("Su canción desactivó la batería.", None),                     # no wake word: nothing
    ("Secuencia, activo la botería.", [{"cmd": "mute", "track": "Batería", "on": False}]),
    ("Secuencia. Desactiva la teoría.", [{"cmd": "mute", "track": "Batería", "on": True}]),
    # as Whisper wrote them with Bryam's mic
    ("Seguencia, repetir el coro", [{"cmd": "repeat"}]),
    ("Se cuesta, ir al final", [{"cmd": "goto", "section": "Final"}]),
    ("Secuencia, Repedir con...", [{"cmd": "repeat"}]),
    ("Se cuencia y ir al coro.", [{"cmd": "goto", "section": "Coro"}]),
    ("secuencia y real final.", [{"cmd": "goto", "section": "Final"}]),
    ("Se cuente ir al verso 1.", [{"cmd": "goto", "section": "Verso 1"}]),
    ("secuencia y racoro.", [{"cmd": "goto", "section": "Coro"}]),          # "ir al coro", glued
    ("secuencia y reprecoro.", [{"cmd": "goto", "section": "Pre coro"}]),   # "ir a precoro", glued
    ("secuencia, alcoro", [{"cmd": "goto", "section": "Coro"}]),
])
def test_phrases(said, commands):
    result = parse(said, SECTIONS, TRACKS, SONGS, current="Coro 1")
    if commands is None:
        assert result is None
    else:
        assert result is not None and result[1] == commands


@pytest.mark.parametrize("said", [
    "Vamos al coro",                                # no wake word
    "Secuencia",                                    # nothing after it
    "Secuencia, qué bonito",                        # nothing we know
    "Secuencia, silencia el violín",                # no such track
    "Su presencia, vamos al coro",                  # rhymes with the wake word
    "Secuencia, con tu poder tu haces nuevo el coro de mi corazón",  # a lyric after an imagined wake word
    "Tu presencia es real, vamos al coro",
])
def test_ignored(said):
    assert parse(said, SECTIONS, TRACKS, SONGS, current="Coro 1") is None


def test_para_stops_only_as_the_first_word():
    assert parse("Secuencia, vamos para el coro", SECTIONS)[1] == [{"cmd": "goto", "section": "Coro"}]


def test_mute_verbs_are_never_guessed():
    # nothing that changes what is heard is done on a guess
    assert parse("Secuencia, activa y silencia la batería", SECTIONS, TRACKS)[1] == []
    assert parse("Secuencia, desactiv la batería", SECTIONS, TRACKS)[1] == []     # near miss: refused


def test_without_wake_word_for_tests():
    assert parse("Puente", SECTIONS, wake_words=())[1] == [{"cmd": "goto", "section": "Puente"}]


SR = 16000


def tone(seconds, db):
    t = np.arange(int(SR * seconds)) / SR
    return (10 ** (db / 20) * np.sqrt(2) * np.sin(2 * np.pi * 300 * t)).astype(np.float32)


def noise(seconds, db, seed=0):
    return (10 ** (db / 20) * np.random.default_rng(seed).standard_normal(int(SR * seconds))).astype(np.float32)


def test_segmenter_cuts_speech_over_bleed():
    # stage bleed at -45 dB, two "phrases" at -20 dB
    stream = np.concatenate([noise(3, -45), noise(1.0, -45, 1) + tone(1.0, -20), noise(2, -45, 2),
                             noise(1.5, -45, 3) + tone(1.5, -20), noise(2, -45, 4)])
    seg = Segmenter(SR)
    found = []
    for i in range(0, len(stream), 800):
        found += seg.feed(stream[i:i + 800])
    assert len(found) == 2
    (s1, a1), (s2, a2) = found
    assert s1 == pytest.approx(3.0 - 0.3, abs=0.1)              # with 300 ms before it
    assert len(a1) / SR == pytest.approx(1.0 + 0.3 + 0.4, abs=0.15)   # + 400 ms after
    assert s2 == pytest.approx(6.0 - 0.3, abs=0.1)


def test_segmenter_caps_long_sounds():
    seg = Segmenter(SR, max_s=2.0)
    found = seg.feed(np.concatenate([noise(1, -60), tone(5, -10), noise(1, -60)]))
    assert len(found) >= 2 and all(len(a) <= 2.05 * SR for _, a in found)


def test_listen_sends_commands_and_reports_them():
    stream = [np.concatenate([noise(1, -60), tone(1, -20), noise(1, -60)])]
    sent, lines = [], []

    def send(msg):
        sent.append(msg)
        return {"ok": True}

    ctx = Context(SECTIONS, TRACKS, SONGS, current="Verso 1")
    listen(iter(stream), SR, lambda audio, prompt: "Secuencia, vamos al coro", lambda: ctx, send=send,
           out=lines.append)
    assert sent == [{"cmd": "goto", "section": "Coro"}, {"cmd": "message", "text": "Voz: Ir a Coro"}]
    assert "✓" in lines[0]


def test_listen_dry_run_and_errors():
    stream = [np.concatenate([noise(1, -60), tone(1, -20), noise(1, -60)])]
    sent, lines = [], []
    listen(iter(stream), SR, lambda a, p: "Secuencia, siguiente", lambda: Context(), dry_run=True,
           send=sent.append, out=lines.append)
    assert sent == [] and "sin enviar" in lines[0]

    def refuse(msg):
        sent.append(msg)
        return {"ok": False, "error": "no hay más secciones"} if msg["cmd"] != "message" else {"ok": True}

    listen(iter(stream), SR, lambda a, p: "Secuencia, siguiente", lambda: Context(), send=refuse,
           out=lines.append)
    assert sent[-1] == {"cmd": "message", "text": "Voz: Siguiente sección — no hay más secciones"}


def test_listen_resamples_interface_rate():
    sr = 48000
    t = np.arange(sr) / sr
    loud = (0.1 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    stream = [np.concatenate([np.zeros(sr, np.float32) + 1e-4, loud, np.zeros(sr, np.float32) + 1e-4])]
    seen = []
    listen(iter(stream), sr, lambda a, p: seen.append(len(a)) or "", lambda: Context(), out=lambda s: None)
    assert seen and seen[0] / 16000 == pytest.approx(1.7, abs=0.15)


def test_wake_word_alone_then_the_order():
    # "Secuencia." … pause … "ir al coro."  (two phrases, as people say it)
    quiet = noise(1, -60)
    stream = [np.concatenate([quiet, tone(0.8, -20), quiet, tone(1, -20), noise(6, -60, 5), tone(1, -20), quiet])]
    said = iter(["Seguencia.", "ir al coro.", "ir al final"])
    sent, lines = [], []

    def send(msg):
        sent.append(msg)
        return {"ok": True}

    listen(iter(stream), SR, lambda a, p: next(said), lambda: Context(SECTIONS, current="Verso 1"),
           send=send, out=lines.append)
    assert sent[0] == {"cmd": "goto", "section": "Coro"}
    assert "te escucho" in lines[0]
    assert len([m for m in sent if m["cmd"] == "goto"]) == 1     # the third came too late: ignored


def test_section_this_song_does_not_have():
    holy = ["Intro", "Verso 1", "Pre coro", "Coro 1", "Verso 2", "Build", "Coro 2", "Tag", "Final"]
    assert parse("secuencia vamos al puente", holy) == ("Esta canción no tiene Puente", [])
    sent, lines = [], []
    stream = [np.concatenate([noise(1, -60), tone(1, -20), noise(1, -60)])]
    listen(iter(stream), SR, lambda a, p: "secuencia vamos al puente", lambda: Context(holy),
           send=lambda m: sent.append(m) or {"ok": True}, out=lines.append)
    assert sent == [{"cmd": "message", "text": "Voz: Esta canción no tiene Puente"}]
    assert "✗" in lines[0]


@pytest.mark.parametrize("said,commands", [
    ("Secuencia, canción uno", [{"cmd": "song", "number": 1}]),
    ("Secuencia, primera canción", [{"cmd": "song", "number": 1}]),
    ("Secuencia, regresamos a la primera canción", [{"cmd": "song", "number": 1}]),
    ("Secuencia, canción anterior", [{"cmd": "song", "number": 1}]),
    ("Secuencia, última canción", [{"cmd": "song", "number": 2}]),
    ("Secuencia, próxima canción", [{"cmd": "next_song"}]),
    ("Secuencia, empezamos con la primera canción", [{"cmd": "song", "number": 1}, {"cmd": "play"}]),
    ("Secuencia, Holy Forever", [{"cmd": "song", "number": 1}]),
])
def test_songs(said, commands):
    assert parse(said, SECTIONS, TRACKS, SONGS, song_number=2)[1] == commands


@pytest.mark.parametrize("said,commands", [
    ("Secuencia, después va la canción tres", [{"cmd": "next_is", "number": 3}]),
    ("Secuencia, luego Holy Forever", [{"cmd": "next_is", "number": 1}]),
    ("Secuencia, la siguiente es la canción tres", [{"cmd": "next_is", "number": 3}]),
    ("Secuencia, saltamos la canción dos", [{"cmd": "skip", "number": 2}]),
    ("Secuencia, quita Alegras mis días", [{"cmd": "skip", "number": 2}]),
    ("Secuencia, siguiente canción", [{"cmd": "next_song"}]),       # unchanged: go now
    ("Secuencia, quita la guía", [{"cmd": "mute", "track": "Guía", "on": True}]),   # not a song
])
def test_changing_the_order(said, commands):
    assert parse(said, SECTIONS, TRACKS, SONGS, song_number=1)[1] == commands


def test_no_song_before_the_first():
    assert parse("Secuencia, canción anterior", SECTIONS, songs=SONGS, song_number=1) == ("Ya es la primera canción", [])


def test_order_split_in_two_phrases():
    # "Secuencia, vamos…" (pause) "…al coro"
    quiet = noise(1, -60)
    stream = [np.concatenate([quiet, tone(0.8, -20), quiet, tone(0.6, -20), quiet])]
    said = iter(["Secuencia, vamos", "al coro"])
    sent = []
    listen(iter(stream), SR, lambda a, p: next(said), lambda: Context(SECTIONS, current="Verso 1"),
           send=lambda m: sent.append(m) or {"ok": True}, out=lambda s: None)
    assert sent[0] == {"cmd": "goto", "section": "Coro"}


def test_record_keeps_each_phrase(tmp_path):
    stream = [np.concatenate([noise(1, -60), tone(1, -20), noise(1, -60)])]
    listen(iter(stream), SR, lambda a, p: "Secuencia, siguiente", lambda: Context(), dry_run=True,
           out=lambda s: None, record=tmp_path)
    rows = (tmp_path / "registro.tsv").read_text().splitlines()
    assert len(rows) == 1 and rows[0].split("\t")[2:4] == ["Secuencia, siguiente", "Siguiente sección"]
    assert len(list(tmp_path.glob("*.wav"))) == 1
