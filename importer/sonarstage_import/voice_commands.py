"""What the director said -> SonarStage Link commands.

Closed vocabulary in Spanish (and the usual English words), after a wake word:

    "Secuencia, repetimos el coro"      repeat (or go to the chorus if we are elsewhere)
    "Secuencia, vamos al puente"        go to the next "Puente" at the end of this section
    "Secuencia, siguiente"              next section
    "Secuencia, seguimos"               release a repeat
    "Secuencia, cancela"                forget the pending jump
    "Secuencia, siguiente canción"      next song (stopped, ready to play)
    "Secuencia, canción tres"           song 3
    "Secuencia, silencia la guitarra"   mute the live backup of a musician; "activa" undoes it
    "Secuencia, dale" / "para"          play / stop

`parse` is pure (text + context in, commands out) so every phrase can be tested.
"""
import difflib
import re
import unicodedata

WAKE_WORDS = ("secuencia",)

NUMBERS = {"uno": 1, "una": 1, "primer": 1, "primero": 1, "primera": 1, "one": 1,
           "dos": 2, "segundo": 2, "segunda": 2, "two": 2,
           "tres": 3, "tercer": 3, "tercero": 3, "tercera": 3, "three": 3,
           "cuatro": 4, "cuarto": 4, "four": 4, "cinco": 5, "quinto": 5, "five": 5,
           "seis": 6, "six": 6, "siete": 7, "seven": 7, "ocho": 8, "eight": 8,
           "nueve": 9, "nine": 9, "diez": 10, "ten": 10, "once": 11, "doce": 12}

# spoken word -> the word used in section names (names come from label.py, in Spanish)
SECTION_WORDS = {"chorus": "coro", "estribillo": "coro", "coros": "coro", "verse": "verso",
                 "estrofa": "verso", "versos": "verso", "bridge": "puente", "precoro": "pre coro",
                 "prechorus": "pre coro", "ending": "final", "outro": "final", "interlude": "interludio",
                 "inicio": "intro", "introduccion": "intro"}

TRACK_WORDS = {"bateria": ("bateria", "drums", "bata", "bate"), "bajo": ("bajo", "bass"),
               "guitarra": ("guitarra", "guitar", "electrica", "guitarras"),
               "teclado": ("teclado", "teclados", "keys", "piano", "teclas"),
               "guia": ("guia", "guide", "cues"), "click": ("click", "clic", "metronomo")}

CANCEL = {"cancela", "cancelar", "cancelalo", "olvidalo", "olvida", "cancel", "anula"}
STOP = {"para", "paramos", "parar", "alto", "detente", "deten", "stop", "corta", "cortamos"}
NEXT = {"siguiente", "proxima", "proximo", "next"}
SONG = {"cancion", "song", "tema"}
MUTE = {"silencia", "silenciar", "silenciamos", "mutea", "mutear", "apaga", "apagar", "quita",
        "quitar", "saca", "sacar", "calla", "mute"}
UNMUTE = {"activa", "activar", "activamos", "prende", "prender", "enciende", "desmutea", "pon",
          "suena", "unmute", "devuelve", "regresa"}
REPEAT = {"repite", "repetimos", "repetir", "repitan", "repeat", "again"}
RELEASE = {"seguimos", "sigue", "suelta", "soltamos", "continua", "continuamos", "continue",
           "avanza", "avanzamos", "salimos", "release"}
PLAY = {"dale", "play", "arranca", "arrancamos", "empieza", "empezamos", "comienza", "comenzamos",
        "inicia", "iniciamos", "adelante"}


def normalize(text):
    """'¡Vamos al Coro Dos!' -> ['vamos', 'al', 'coro', '2']"""
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"pre[\s-]+(coro|chorus)", r"pre\1", t)
    tokens = re.findall(r"[a-z0-9]+", t)
    return [str(NUMBERS[w]) if w in NUMBERS else SECTION_WORDS.get(w, w) for w in tokens]


def _section_tokens(name):
    return normalize(name)


def _like(heard, word):
    """Whisper bends long words ("Perso", "Instrumentar"): close enough counts, from 5 letters."""
    if heard == word:
        return True
    return min(len(heard), len(word)) >= 5 and difflib.SequenceMatcher(None, heard, word).ratio() >= 0.7


def _contains(tokens, seq, fuzzy=False):
    n = len(seq)
    same = (lambda a, b: all(_like(x, y) for x, y in zip(a, b))) if fuzzy else (lambda a, b: a == b)
    return n > 0 and any(same(tokens[i:i + n], seq) for i in range(len(tokens) - n + 1))


def after_wake_word(tokens, wake_words=WAKE_WORDS, within=3):
    """Tokens after the wake word, or None if it was not said. It has to open the phrase
    (first `within` words): a sung line that happens to contain it does not count."""
    last = None
    for i, w in enumerate(tokens[:within]):
        if any(difflib.SequenceMatcher(None, w, k).ratio() >= 0.8 for k in wake_words):
            last = i
    return None if last is None else tokens[last + 1:]


def find_section(tokens, sections):
    """The section named in `tokens`: an exact name ("Verso 2") beats the bare word
    ("coro", which the bridge resolves to the next "Coro 1"/"Coro 2")."""
    best = None
    for name in sections:
        full = _section_tokens(name)
        base = full[:-1] if len(full) > 1 and full[-1].isdigit() else full
        for seq, value in ((full, name), (base, " ".join(base))):
            if _contains(tokens, seq, fuzzy=True) and (best is None or len(seq) > best[0]):
                best = (len(seq), value)
    return best[1] if best else None


def find_track(tokens, tracks):
    for name in tracks:
        words = set(_section_tokens(name))
        spoken = set()
        for key, aliases in TRACK_WORDS.items():
            if key in words:
                spoken.update(aliases)
        spoken.update(w for w in words if len(w) >= 4)
        if spoken & set(tokens):
            return name
    return None


def _number(tokens):
    return next((int(w) for w in tokens if w.isdigit()), None)


def parse(text, sections=(), tracks=(), songs=(), current=None, wake_words=WAKE_WORDS):
    """(description, [commands]) or None.

    sections: names in the current song; tracks: muteable tracks; songs: [(number, title)];
    current: name of the section playing. wake_words=() means no wake word is needed.
    """
    tokens = normalize(text)
    if wake_words:
        tokens = after_wake_word(tokens, wake_words)
        if not tokens:
            return None
    if not tokens:
        return None
    words = set(tokens)

    if words & CANCEL:
        return "Cancelar", [{"cmd": "cancel"}]
    if tokens[0] in STOP:
        return "Parar", [{"cmd": "stop"}]

    if words & SONG or ("next" in words and "song" in words):
        if words & NEXT:
            return "Siguiente canción", [{"cmd": "next_song"}]
        n = _number(tokens)
        if n is not None:
            return "Canción %d" % n, [{"cmd": "song", "number": n}]
    for number, title in songs:
        if len(normalize(title)) >= 2 and _contains(tokens, normalize(title)[:2]):
            return "Canción %d · %s" % (number, title), [{"cmd": "song", "number": number}]

    if words & (MUTE | UNMUTE):
        track = find_track(tokens, tracks)
        if track:
            mute = bool(words & MUTE)
            return ("Silenciar " if mute else "Activar ") + track, [{"cmd": "mute", "track": track, "on": mute}]

    section = find_section(tokens, sections)
    repeat = bool(words & REPEAT) or _contains(tokens, ["otra", "vez"]) or _contains(tokens, ["de", "nuevo"]) \
        or _contains(tokens, ["vez", "mas"])
    if repeat and (section is None or _same_section(section, current)):
        return "Repetir" + (" " + current if current else ""), [{"cmd": "repeat"}]
    if section:
        shown = section[:1].upper() + section[1:]
        if words & PLAY:
            return "Desde " + shown, [{"cmd": "goto", "section": section}, {"cmd": "play"}]
        return "Ir a " + shown, [{"cmd": "goto", "section": section}]
    if words & RELEASE:
        return "Seguir", [{"cmd": "release"}]
    if words & NEXT:
        return "Siguiente sección", [{"cmd": "next_section"}]
    if words & PLAY:
        return "Play", [{"cmd": "play"}]
    return None


def _same_section(spoken, current):
    if not current:
        return True
    a, b = _section_tokens(spoken), _section_tokens(current)
    return a == b or a == b[:len(a)]
