"""The real surface.py, with stand-ins for the modules that only exist inside Ableton."""
import os
import sys
import threading
import time
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test_core import CUES, FakeSong  # noqa: E402


@pytest.fixture
def surface_cls(monkeypatch):
    live = types.ModuleType("Live")
    live.Song = types.SimpleNamespace(Quantization=types.SimpleNamespace(q_bar="q_bar"))

    class ControlSurface(object):              # what Live 12's ableton.v2 provides that we use
        def __init__(self, c_instance):
            self._song = c_instance
            self.scheduled = []
            self.messages = []

        @property
        def song(self):
            return self._song

        def schedule_message(self, delay, callback):
            self.scheduled.append(callback)

        def show_message(self, msg):
            self.messages.append(msg)

        def disconnect(self):
            pass

    cs = types.ModuleType("ableton.v2.control_surface")
    cs.ControlSurface = ControlSurface
    for name, mod in (("Live", live), ("ableton", types.ModuleType("ableton")),
                      ("ableton.v2", types.ModuleType("ableton.v2")), ("ableton.v2.control_surface", cs)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "SonarStageLink.surface", raising=False)
    from SonarStageLink import surface
    monkeypatch.setattr(surface, "PORT", 0)      # any free port
    return surface


def test_tcp_requests_are_answered_from_the_tick(surface_cls, monkeypatch):
    import link
    song = FakeSong(CUES)
    s = surface_cls.SonarStageLink(song)
    assert s.messages == ["SonarStage Link conectado"]
    monkeypatch.setattr(link, "ADDR", s._server.getsockname())

    stop = threading.Event()

    def live_main_thread():                      # Live calls the scheduled tick ~10 times a second
        while not stop.is_set():
            cb = s.scheduled.pop(0)
            cb()
            time.sleep(0.01)

    t = threading.Thread(target=live_main_thread, daemon=True)
    t.start()
    try:
        r = link.send({"cmd": "status"})
        assert r["ok"] and r["state"]["song_title"] == "Holy Forever"
        assert link.send({"cmd": "goto", "section": "Sección 2"})["state"]["section"] == "Sección 2"
        assert not link.send({"cmd": "nada"})["ok"]
        for _ in range(12):                       # more requests than MAX_CLIENTS: closed ones are dropped
            assert link.send({"cmd": "status"})["ok"]
        assert len(s._clients) <= surface_cls.MAX_CLIENTS
    finally:
        stop.set()
        t.join(1)
        s.disconnect()
