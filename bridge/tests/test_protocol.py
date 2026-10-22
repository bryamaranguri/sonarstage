"""link.py ↔ a TCP server running LinkCore, the same exchange the Remote Script does."""
import json
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import link  # noqa: E402
from SonarStageLink.core import LinkCore  # noqa: E402
from test_core import CUES, FakeSong, Q_BAR  # noqa: E402


def serve(core, server, stop):
    """Same exchange as surface.py: one JSON line in, one JSON line out, over TCP."""
    server.settimeout(0.05)
    while not stop.is_set():
        try:
            conn, _ = server.accept()
        except socket.timeout:
            continue
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            try:
                reply = core.handle(json.loads(data.decode("utf-8")))
            except ValueError as e:
                reply = {"ok": False, "error": "mensaje inválido: %s" % e}
            conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))


def test_commands_over_tcp(monkeypatch):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)
    monkeypatch.setattr(link, "ADDR", sock.getsockname())
    song = FakeSong(CUES)
    stop = threading.Event()
    t = threading.Thread(target=serve, args=(LinkCore(song, bar_quantization=Q_BAR), sock, stop), daemon=True)
    t.start()
    try:
        assert link.main(["goto", "Sección", "2"]) == 0 and song.current_song_time == 24
        assert link.main(["play"]) == 0 and song.is_playing
        assert link.main(["repeat"]) == 0 and song.loop
        assert link.main(["mute", "Bajo"]) == 0 and song.tracks[1].mute
        assert link.main(["goto", "Coro"]) == 1                       # unknown section: clear error
        r = link.send({"cmd": "status"})
        assert r["state"]["section"] == "Sección 2" and r["state"]["loop"]
        assert "repitiendo" in link.describe(r["state"])
    finally:
        stop.set()
        t.join(1)
        sock.close()


def test_no_ableton_gives_a_clear_message(monkeypatch):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()
    s.close()                                                        # nobody listening there
    monkeypatch.setattr(link, "ADDR", port)
    r = link.send({"cmd": "status"}, timeout=0.3)
    assert not r["ok"] and "Ableton no responde" in r["error"]
