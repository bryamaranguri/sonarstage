"""End-to-end preparation of a synthetic pack, plus pack-safety checks."""
import json
import zipfile

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf

from sonarstage_import import library, printing
from sonarstage_import.extract import PackError, extract_pack
from sonarstage_import.prepare import prepare

from test_analysis import SR, click_track

BPM = 120
SECONDS = 24


def _stereo(x):
    return np.stack([x, x], axis=1).astype(np.float32)


def _kick_on_beats(level=0.9):
    x = np.zeros(SR * SECONDS, dtype=np.float32)
    t = np.arange(int(0.12 * SR)) / SR
    kick = level * np.sin(2 * np.pi * 55 * t) * np.exp(-t * 30)
    for k, start in enumerate(np.arange(0, SECONDS - 0.2, 60 / BPM)):
        amp = 1.0 if k % 4 == 0 else 0.4            # stronger on beat 1
        i = int(start * SR)
        x[i:i + len(kick)] += amp * kick
    return _stereo(x)


def _guide_cues(bars=(1, 3, 7)):
    x = np.zeros(SR * SECONDS, dtype=np.float32)
    bar_s = 4 * 60 / BPM
    t = np.arange(int(0.5 * SR)) / SR
    word = 0.5 * np.sin(2 * np.pi * 220 * t) * np.sin(np.pi * t / 0.5)
    for b in bars:
        i = int((b - 1) * bar_s * SR)
        x[i:i + len(word)] += word
    return _stereo(x)


def _pad(level=0.8):
    t = np.arange(SR * SECONDS) / SR
    return _stereo(level * np.sin(2 * np.pi * 330 * t))


@pytest.fixture
def pack(tmp_path):
    files = {
        "Click.wav": click_track(bpm=BPM, seconds=SECONDS),
        "Drums.wav": _kick_on_beats(),
        "Guide.wav": _guide_cues(),
        "Pad.wav": _pad(),
    }
    z = tmp_path / "MT TEST SONG.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name, data in files.items():
            p = tmp_path / name
            sf.write(p, data, SR, subtype="PCM_24")
            zf.write(p, f"TEST SONG/{name}")
            p.unlink()
    return z


def test_prepare_end_to_end(pack, tmp_path):
    lib = tmp_path / "Biblioteca"
    song_dir, song, report = prepare(pack, lib, quiet=True)

    assert song_dir.name == "Test Song"
    assert library.validate(song) is None
    assert json.loads((song_dir / "cancion.json").read_text())["tempo"]["bpm"] == pytest.approx(120, abs=0.1)
    assert song["sections"][0]["startBar"] == 1
    assert [s["startBar"] for s in song["sections"]] == [1, 3, 7]

    printed = {p.stem: sf.read(p) for p in (song_dir / "preparada" / "0").glob("*.flac")}
    assert set(printed) == {"Click", "Drums", "Guide", "Pad"}
    # music stems got one common gain; their sum respects the target or the peak ceiling
    mix = printed["Drums"][0] + printed["Pad"][0]
    lufs = pyln.Meter(SR).integrated_loudness(mix)
    peak = 20 * np.log10(np.abs(mix).max())
    assert peak <= printing.PEAK_CEILING_DBFS + 0.1
    assert lufs == pytest.approx(printing.TARGET_LUFS, abs=0.3) or peak >= printing.PEAK_CEILING_DBFS - 0.2
    gains = {s["label"]: s["gainDb"] for s in song["stems"]}
    assert gains["Drums"] == gains["Pad"]
    # originals untouched and kept as they came
    assert (song_dir / "originales" / "Click.wav").exists()


def test_refuses_to_overwrite_a_song(pack, tmp_path):
    lib = tmp_path / "Biblioteca"
    prepare(pack, lib, quiet=True)
    with pytest.raises(PackError):
        prepare(pack, lib, quiet=True)


def test_rejects_path_traversal(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../escape.wav", b"x")
    with pytest.raises(PackError):
        extract_pack(z, tmp_path / "out")
    assert not (tmp_path.parent / "escape.wav").exists()


def test_skips_non_audio_and_mac_metadata(tmp_path):
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Song/Click.wav", b"RIFF")
        zf.writestr("Song/readme.txt", b"hola")
        zf.writestr("__MACOSX/Song/._Click.wav", b"junk")
    written = extract_pack(z, tmp_path / "out")
    assert [p.name for p in written] == ["Click.wav"]


def test_song_gain_respects_peak_ceiling():
    gain, reason = printing.plan_song_gain(mix_lufs=-11.7, mix_peak_db=4.4, stem_peaks_db=[-0.3], target_lufs=-16)
    assert gain == pytest.approx(-5.4)
    assert reason == "pico de la mezcla"
    gain, reason = printing.plan_song_gain(mix_lufs=-16.8, mix_peak_db=-0.2, stem_peaks_db=[-2.6], target_lufs=-16)
    assert gain == pytest.approx(-0.8) and reason == "pico de la mezcla"


def test_title_from_source():
    assert library.title_from_source("MT HOLY FOREVER BETHEL MUSIC.rar") == "Holy Forever Bethel Music"
    assert library.title_from_source("ALEGRAS MIS DIAS - SU PRESENCIA.rar") == "Alegras Mis Dias - Su Presencia"
