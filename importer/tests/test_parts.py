"""Parts matrix: who covers which stem in which section, and how the show splits it."""
import json

import numpy as np
import pytest
import soundfile as sf

from sonarstage_import import parts
from sonarstage_import.render import RenderError, render_song

SR = 44100
BPM = 120                 # 2 s per 4/4 bar
SECONDS = 20              # 10 bars


def tone(hz, level=0.3):
    t = np.arange(SR * SECONDS) / SR
    x = (level * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


@pytest.fixture
def song_dir(tmp_path):
    """Hand-made library song: sections at bars 1 (2 bars), 3 (4 bars), 7 (4 bars)."""
    d = tmp_path / "Canción"
    (d / "originales").mkdir(parents=True)
    stems = {"Click": ("click", tone(1000, 0.1)), "EG 1": ("eg", tone(220)), "EG 2": ("eg", tone(440)),
             "Bass": ("bass", tone(55)), "Pad": ("pad", tone(330, 0.1))}
    for label, (_, x) in stems.items():
        sf.write(d / "originales" / f"{label}.wav", x, SR, subtype="FLOAT")
    song = {
        "schemaVersion": 1, "id": "cancion", "title": "Canción",
        "tempo": {"bpm": BPM, "timeSignature": "4/4", "map": [], "firstDownbeatSec": 0.0},
        "key": {"original": "C"},
        "sections": [{"name": "Cuenta", "kind": "other", "startBar": 1, "bars": 2},
                     {"name": "Verso", "kind": "verse", "startBar": 3, "bars": 4},
                     {"name": "Coro", "kind": "chorus", "startBar": 7, "bars": 4}],
        "stems": [{"file": f"{label}.wav", "role": role, "label": label, "harmonic": role != "click",
                   "gainDb": 0.0} for label, (role, _) in stems.items()],
    }
    (d / "cancion.json").write_text(json.dumps(song))
    return d


@pytest.fixture
def band(tmp_path):
    b = {"schemaVersion": 1, "id": "mi-banda", "name": "Mi banda", "musicians": [
        {"id": "guitarra", "name": "Guitarra", "role": "eg", "default": ["EG 1"]},
        {"id": "bajo", "name": "Bajo", "role": "bass", "default": ["Bass"]},
        {"id": "teclado", "name": "Teclado", "role": "keys", "default": ["Keys 1"]}]}
    path = tmp_path / "mi-banda.json"
    path.write_text(json.dumps(b))
    return parts.load_band(path)


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


def dominant_hz(x):
    m = x.mean(axis=1)
    spec = np.abs(np.fft.rfft(m * np.hanning(len(m))))
    return np.fft.rfftfreq(len(m), 1 / SR)[np.argmax(spec)]


def song_of(d):
    return json.loads((d / "cancion.json").read_text())


def test_default_covers_the_whole_song(song_dir, band):
    cov, warnings = parts.coverage(song_of(song_dir), band)
    assert {r["id"]: r["stems"] for r in cov} == {"guitarra": {"EG 1": None}, "bajo": {"Bass": None}, "teclado": {}}
    assert warnings and "Keys 1" in warnings[0]


def test_matrix_by_section(song_dir, band):
    parts.set_parts(song_dir, band, "guitarra", ["2=EG 1", "3=EG 1+EG 2"])
    song = song_of(song_dir)
    assert song["parts"]["mi-banda"]["guitarra"] == {"3": ["EG 1"], "7": ["EG 1", "EG 2"]}
    cov, _ = parts.coverage(song, band, ["guitarra"])
    assert cov[0]["stems"] == {"EG 1": {3, 7}, "EG 2": {7}}


def test_conflicting_matrices_are_refused(song_dir, band):
    band["musicians"].append({"id": "guitarra-2", "name": "Guitarra 2", "role": "eg", "default": ["EG 2"]})
    parts.set_parts(song_dir, band, "guitarra", ["3=EG 2"])
    with pytest.raises(parts.PartsError):        # guitarra-2 covers EG 2 everywhere by default
        parts.coverage(song_of(song_dir), band)
    parts.coverage(song_of(song_dir), band, ["guitarra"])     # fine if only one of them plays


def test_bad_specs(song_dir, band):
    with pytest.raises(parts.PartsError):
        parts.set_parts(song_dir, band, "guitarra", ["4=EG 1"])          # only 3 sections
    with pytest.raises(parts.PartsError):
        parts.set_parts(song_dir, band, "guitarra", ["2=EG 9"])          # no such stem
    with pytest.raises(parts.PartsError):
        parts.set_parts(song_dir, band, "nadie", ["2=EG 1"])


def test_render_splits_by_section_and_adds_up(song_dir, band, tmp_path):
    parts.set_parts(song_dir, band, "guitarra", ["2=EG 1", "3=EG 2"])
    m = render_song(song_dir, tmp_path / "show", sample_rate=SR, band=band, present=["guitarra", "bajo"])
    groups = {f["label"]: f["group"] for f in m["files"]}
    assert groups == {"Click": "CUES", "Guitarra": "EN VIVO", "Bajo": "EN VIVO", "Secuencia": "SECUENCIA"}
    gtr, _ = sf.read(tmp_path / "show" / "Guitarra.wav", dtype="float32")
    seq, _ = sf.read(tmp_path / "show" / "Secuencia.wav", dtype="float32")
    bass, _ = sf.read(tmp_path / "show" / "Bajo.wav", dtype="float32")
    bar = 2 * SR
    count, verse, chorus = slice(0, 2 * bar - 2000), slice(2 * bar + 2000, 6 * bar - 2000), slice(6 * bar + 2000, None)
    assert rms(gtr[count]) < 1e-4                              # guitarist does not play the count-in
    assert dominant_hz(gtr[verse]) == pytest.approx(220, abs=2)  # EG 1 in the verse
    assert dominant_hz(gtr[chorus]) == pytest.approx(440, abs=2)  # EG 2 in the chorus
    assert dominant_hz(bass) == pytest.approx(55, abs=1)
    # live + sequence rebuild every music stem exactly, crossfades included
    full = sum(sf.read(song_dir / "originales" / f"{n}.wav", dtype="float32")[0] for n in ("EG 1", "EG 2", "Bass", "Pad"))
    assert np.max(np.abs(gtr + bass + seq - full)) < 1e-4
    live = {f["label"]: f["contains"] for f in m["files"] if f["group"] == "EN VIVO"}
    assert live == {"Guitarra": {"EG 1": [3], "EG 2": [7]}, "Bajo": {"Bass": "todo"}}


def test_absent_musician_goes_to_the_sequence(song_dir, band, tmp_path):
    m = render_song(song_dir, tmp_path / "show", sample_rate=SR, band=band, present=["guitarra"])
    seq = next(f for f in m["files"] if f["group"] == "SECUENCIA")
    assert "Bass" in seq["contains"] and "EG 1" not in seq["contains"]


def test_band_and_live_are_exclusive(song_dir, band, tmp_path):
    with pytest.raises(RenderError):
        render_song(song_dir, tmp_path / "show", band=band, live=["drums"])


def test_mask_ramps_are_complementary():
    bounds = [(1, 0, 1000), (3, 1000, 3000), (7, 3000, 5000)]
    a = parts.mask(5000, bounds, {3}, SR)
    b = parts.mask(5000, bounds, {1, 7}, SR)
    assert np.allclose(a + b, 1.0, atol=1e-6)
    assert a[500] == 0 and a[2000] == 1 and 0 < a[1000] < 1


def test_command_line_set_and_show(song_dir, band, tmp_path, capsys):
    band_path = tmp_path / "mi-banda.json"
    assert parts.main(["set", str(song_dir), "--band", str(band_path), "--musician", "guitarra",
                       "--secciones", "2=EG 1", "3=EG 2"]) == 0
    assert song_of(song_dir)["parts"]["mi-banda"]["guitarra"] == {"3": ["EG 1"], "7": ["EG 2"]}
    assert parts.main(["show", str(song_dir), "--band", str(band_path), "--presentes", "guitarra"]) == 0
    out = capsys.readouterr().out
    assert "Verso" in out and "EG 1" in out and "no toca" in out
    assert parts.main(["clear", str(song_dir), "--band", str(band_path), "--musician", "guitarra"]) == 0
    assert "parts" not in song_of(song_dir)
