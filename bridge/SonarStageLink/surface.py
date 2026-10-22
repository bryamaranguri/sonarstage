"""Ableton side of SonarStage Link.

TCP server on 127.0.0.1:11010 (only this Mac). Each message is one line of JSON; each
gets one line of JSON back with the result and the current state. TCP rather than UDP:
the reply travels over the connection the client opened, which macOS's firewall lets
through (UDP replies to python3 were dropped on a real Mac).

Everything runs on Live's main thread from a tick scheduled every ~100 ms, with
non-blocking sockets, so nothing ever waits and no threads touch the Live API.
"""
import errno
import json
import logging
import socket

import Live
from ableton.v2.control_surface import ControlSurface

from .core import LinkCore

# Live 12's ControlSurface has no logging method of its own: the logging module
# writes to Live's Log.txt
logger = logging.getLogger("SonarStageLink")


def _log(msg):
    logger.info(msg)


HOST, PORT = "127.0.0.1", 11010
REFRESH_TICKS = 20          # re-read locators every ~2 s (names or times may be edited)
MAX_CLIENTS = 8
MAX_LINE = 65536
WOULD_BLOCK = (errno.EAGAIN, errno.EWOULDBLOCK)


class _Client(object):
    def __init__(self, sock, addr):
        self.sock, self.addr, self.inbox = sock, addr, b""


class SonarStageLink(ControlSurface):

    def __init__(self, c_instance):
        super(SonarStageLink, self).__init__(c_instance)
        self._live_song = self.song() if callable(self.song) else self.song
        self.core = LinkCore(self._live_song, bar_quantization=Live.Song.Quantization.q_bar, log=_log,
                              notify=self.show_message)
        self._ticks = 0
        self._clients = []
        self._server = None
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind((HOST, PORT))
            self._server.listen(MAX_CLIENTS)
            self._server.setblocking(False)
            _log("escuchando (TCP) en %s:%d" % (HOST, PORT))
            self.show_message("SonarStage Link conectado")
        except Exception as e:
            _log("no se pudo abrir el puerto %d: %r" % (PORT, e))
            self.show_message("SonarStage Link: puerto %d ocupado" % PORT)
            self._server = None
        self.schedule_message(1, self._tick)

    def _tick(self):
        try:
            self._ticks += 1
            if self._ticks % REFRESH_TICKS == 0:
                self.core.refresh()
            self._accept()
            for c in list(self._clients):
                self._serve(c)
            self.core.tick()
        except Exception as e:
            _log("error en el ciclo: %r" % (e,))
        self.schedule_message(1, self._tick)

    def _accept(self):
        if self._server is None:
            return
        while len(self._clients) < MAX_CLIENTS:
            try:
                sock, addr = self._server.accept()
            except (BlockingIOError, socket.error):
                return
            sock.setblocking(False)
            self._clients.append(_Client(sock, addr))

    def _drop(self, c):
        try:
            c.sock.close()
        except Exception:
            pass
        if c in self._clients:
            self._clients.remove(c)

    def _serve(self, c):
        while True:
            try:
                chunk = c.sock.recv(4096)
            except socket.error as e:
                if getattr(e, "errno", None) in WOULD_BLOCK or isinstance(e, BlockingIOError):
                    break
                self._drop(c)
                return
            if not chunk:                      # client closed the connection
                self._drop(c)
                return
            c.inbox += chunk
            if len(c.inbox) > MAX_LINE:
                self._drop(c)
                return
        while b"\n" in c.inbox:
            line, c.inbox = c.inbox.split(b"\n", 1)
            if line.strip():
                self._reply(c, line)

    def _reply(self, c, line):
        try:
            reply = self.core.handle(json.loads(line.decode("utf-8")))
        except ValueError as e:
            reply = {"ok": False, "error": "mensaje inválido: %s" % e}
        except Exception as e:
            _log("error al atender %r: %r" % (line[:200], e))
            reply = {"ok": False, "error": repr(e)}
        try:
            c.sock.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        except Exception as e:
            _log("no se pudo responder a %s: %r" % (c.addr, e))
            self._drop(c)

    def disconnect(self):
        for c in list(self._clients):
            self._drop(c)
        if self._server is not None:
            self._server.close()
            self._server = None
        super(SonarStageLink, self).disconnect()
