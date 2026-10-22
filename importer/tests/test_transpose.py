"""Key changes on a synthetic pack (needs the Rubber Band tool, v3+ for the R3 engine)."""
import json

import numpy as np
import pytest
import soundfile as sf

from sonarstage_import.prepare import prepare
from sonarstage_import.render import RenderError, render_song
from sonarstage_import.transpose import TransposeError, rubberband_available, transpose_song

from test_prepare import pack  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not rubberband_available(), reason="sin Rubber Band 3+")

PAD_HZ = 330.0


def dominant_hz(x, sr):
    mono = x.mean(axis=1) if x.ndim == 2 else x
    seg = mono[sr * 4:sr * 12]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    return freqs[np.argmax(spec)]


@pytest.fixture
def song_dir(pack, tmp_path):  # noqa: F811
    d, _, _ = prepare(pack, tmp_path / "Biblioteca", quiet=True)
    return d


def test_only_harmonic_stems_change_key(song_dir):
    r = transpose_song(song_dir, -2)
    files = sorted(p.name for p in (song_dir / "preparada" / "-2").iterdir())
    assert files == ["Pad.flac"]                        # click, guide and drums untouched
    assert set(r["untouched"]) == {"Click", "Guide", "Drums"}
    x, sr = sf.read(song_dir / "preparada" / "-2" / "Pad.flac")
    orig, _ = sf.read(song_dir / "originales" / "Pad.wav")
    assert len(x) == len(orig)                          # sample-exact length
    assert dominant_hz(x, sr) == pytest.approx(PAD_HZ * 2 ** (-2 / 12), rel=0.01)
    assert json.loads((song_dir / "cancion.json").read_text())["key"]["prepared"] == [-2]


def test_render_uses_the_transposed_version(song_dir, tmp_path):
    transpose_song(song_dir, 3)
    m = render_song(song_dir, tmp_path / "show", sample_rate=48000, live=["drums"], semitones=3)
    seq, sr = sf.read(tmp_path / "show" / "Secuencia.wav")
    assert dominant_hz(seq, sr) == pytest.approx(PAD_HZ * 2 ** (3 / 12), rel=0.01)
    click_show, _ = sf.read(tmp_path / "show" / "Click.wav")
    click_orig, _ = sf.read(song_dir / "originales" / "Click.wav")
    assert len(click_show) == pytest.approx(len(click_orig) * 48000 / 44100, abs=2)
    assert m["semitones"] == 3


def test_rejects_bad_requests(song_dir):
    with pytest.raises(TransposeError):
        transpose_song(song_dir, 0)
    with pytest.raises(TransposeError):
        transpose_song(song_dir, 7)
    transpose_song(song_dir, 1)
    with pytest.raises(TransposeError):
        transpose_song(song_dir, 1)                     # already exists
    with pytest.raises(RenderError):
        render_song(song_dir, song_dir.parent / "x", semitones=-1)


@pytest.mark.parametrize("semitones", [-3, -2, 2, 3])
def test_shifter_delay_is_compensated(semitones):
    from sonarstage_import import transpose as tp
    sr = 44100
    x = tp._burst_signal(sr)
    raw = tp._shift_audio(x, semitones, "keys", sr)
    fixed = tp._align(raw, tp.measure_offset_samples(semitones, sr), len(x))
    assert len(fixed) == len(x)
    assert abs(tp.burst_lag_ms(x, fixed, sr)) <= 0.6        # sub-ms residual after compensation


def test_uses_the_r3_engine_offline():
    from sonarstage_import import transpose as tp
    assert tp.rubberband_version()[0] >= 3
    args = tp.rubberband_args(-2, "eg")
    assert "--fine" in args and "--realtime" not in args and "-R" not in args
    assert "--formant" not in args and "--formant" in tp.rubberband_args(-2, "leadVocal")
