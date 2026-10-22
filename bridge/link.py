#!/usr/bin/env python3
"""Talk to SonarStage Link from the Terminal (for testing; the app will do this).

    python3 link.py status
    python3 link.py play | stop | repeat | release | next | cancel
    python3 link.py goto "Sección 3"          (in the current song, at the end of this section)
    python3 link.py song 2 | next-song
    python3 link.py mute "Bajo" | unmute "Bajo"
    python3 link.py autostop on|off
    python3 link.py watch                     (state twice per second; Ctrl+C to quit)
"""
import json
import socket
import sys
import time

ADDR = ("127.0.0.1", 11010)


def send(msg, timeout=1.0):
    """One request over TCP: a line of JSON out, a line of JSON back."""
    try:
        with socket.create_connection(ADDR, timeout=timeout) as s:
            s.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.decode("utf-8"))
    except (ConnectionRefusedError, socket.timeout, OSError, ValueError):
        return {"ok": False, "error": "Ableton no responde: ¿está abierto con SonarStage Link activo?"}


def describe(st):
    if not st:
        return ""
    where = "%s · %s" % (st["song_title"], st["section"]) if st["section"] else "sin locators"
    bar = " (compás %s de %s)" % (st["section_bar"], st["section_bars"]) if st["section_bars"] else ""
    flags = [("▶ sonando" if st["playing"] else "■ detenido"), "%.1f BPM" % st["tempo"]]
    if st["loop"]:
        flags.append("repitiendo")
    if st["pending"]:
        flags.append("→ irá a %s" % st["pending"])
    return "%s%s  [%s]" % (where, bar, ", ".join(flags))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    simple = {"status": "status", "play": "play", "stop": "stop", "repeat": "repeat", "release": "release",
              "next": "next_section", "cancel": "cancel", "next-song": "next_song"}
    if cmd == "watch":
        try:
            while True:
                r = send({"cmd": "status"})
                print("\r" + (describe(r.get("state")) or r.get("error", "")).ljust(110), end="", flush=True)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()
            return 0
    if cmd in simple:
        msg = {"cmd": simple[cmd]}
    elif cmd == "goto" and args:
        msg = {"cmd": "goto", "section": " ".join(args)}
    elif cmd == "song" and args:
        msg = {"cmd": "song", "number": int(args[0])}
    elif cmd in ("mute", "unmute") and args:
        msg = {"cmd": "mute", "track": " ".join(args), "on": cmd == "mute"}
    elif cmd == "autostop" and args:
        msg = {"cmd": "autostop", "on": args[0] == "on"}
    else:
        print(__doc__)
        return 1
    r = send(msg)
    print(("✓ " if r.get("ok") else "✗ " + r.get("error", "") + "\n  ") + describe(r.get("state")))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
