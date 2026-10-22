"""Ableton side of SonarStage Link.

Listens for JSON commands on UDP 127.0.0.1:11010 (only this Mac) and answers each one
to its sender with the result and the current state. Everything runs on Live's main
thread from a tick scheduled every ~100 ms, so no threads touch the Live API.
"""
import json
import socket

import Live
from ableton.v2.control_surface import ControlSurface

from .core import LinkCore

HOST, PORT = "127.0.0.1", 11010
REFRESH_TICKS = 20          # re-read locators every ~2 s (names or times may be edited)
MAX_PACKET = 65507


class SonarStageLink(ControlSurface):

    def __init__(self, c_instance):
        super(SonarStageLink, self).__init__(c_instance)
        self._live_song = self.song() if callable(self.song) else self.song
        self.core = LinkCore(self._live_song, bar_quantization=Live.Song.Quantization.q_bar,
                             log=self.log_message)
        self._ticks = 0
        self._sock = None
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((HOST, PORT))
            self._sock.setblocking(False)
            self.log_message("SonarStageLink: escuchando en %s:%d" % (HOST, PORT))
            self.show_message("SonarStage Link conectado")
        except Exception as e:
            self.log_message("SonarStageLink: no se pudo abrir el puerto %d: %r" % (PORT, e))
            self.show_message("SonarStage Link: puerto %d ocupado" % PORT)
        self.schedule_message(1, self._tick)

    def _tick(self):
        try:
            self._ticks += 1
            if self._ticks % REFRESH_TICKS == 0:
                self.core.refresh()
            self._poll()
            self.core.tick()
        except Exception as e:
            self.log_message("SonarStageLink: %r" % (e,))
        self.schedule_message(1, self._tick)

    def _poll(self):
        if self._sock is None:
            return
        while True:
            try:
                data, addr = self._sock.recvfrom(MAX_PACKET)
            except (BlockingIOError, socket.error):
                return
            try:
                msg = json.loads(data.decode("utf-8"))
                reply = self.core.handle(msg)
            except ValueError as e:
                reply = {"ok": False, "error": "mensaje inválido: %s" % e}
            self._sock.sendto(json.dumps(reply).encode("utf-8"), addr)

    def disconnect(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        super(SonarStageLink, self).disconnect()
