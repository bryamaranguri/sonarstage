"""Client for SonarStage Link (the Remote Script inside Ableton): one line of JSON per
request over TCP on 127.0.0.1:11010, one line of JSON back."""
import json
import socket

ADDR = ("127.0.0.1", 11010)
NOT_RUNNING = "Ableton no responde: ¿está abierto con SonarStage Link activo?"


def send(msg, timeout=1.0, addr=ADDR):
    try:
        with socket.create_connection(addr, timeout=timeout) as s:
            s.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": NOT_RUNNING}
