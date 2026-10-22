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
                 "estrofa": "verso", "versos": "verso", "bridge": "puente", "precoro": "precoro",
                 "prechorus": "precoro", "ending": "final", "outro": "final", "interlude": "interludio",
                 "inicio": "intro", "introduccion": "intro"}

# section words any song may have (names as label.py writes them, normalized)
GENERIC_SECTIONS = {"intro": "Intro", "verso": "Verso", "precoro": "Pre coro", "coro": "Coro",
                    "puente": "Puente", "instrumental": "Instrumental", "interludio": "Interludio",
                    "tag": "Tag", "final": "Final", "build": "Build", "break": "Break", "vamp": "Vamp"}

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


def _is_wake(word, wake_words, ratio=0.8):
    """Close to the wake word and starting like it: "seguencia" yes, "presencia" no
    (it rhymes, and "tu presencia" is all over worship lyrics)."""
    return any(word[:2] == k[:2] and difflib.SequenceMatcher(None, word, k).ratio() >= ratio
               for k in wake_words)


def after_wake_word(tokens, wake_words=WAKE_WORDS, within=3):
    """Tokens after the wake word, or None if it was not said. It has to open the phrase
    (first `within` words): a sung line that happens to contain it does not count.
    Whisper sometimes splits it ("Se cuesta"), so two words together also count."""
    last = None
    for i in range(min(within, len(tokens))):
        if _is_wake(tokens[i], wake_words):
            last = i
        elif i + 1 < len(tokens) and _is_wake(tokens[i] + tokens[i + 1], wake_words, 0.7):
            last = i + 1
    return None if last is None else tokens[last + 1:]


def is_wake_only(text, wake_words=WAKE_WORDS):
    """Just "Secuencia": the order comes in the next phrase (people pause after it)."""
    rest = after_wake_word(normalize(text), wake_words)
    return rest is not None and not rest


def _has(tokens, vocabulary):
    """A word of `vocabulary` was said; long ones may be a bit off ("repedir")."""
    for w in tokens:
        if w in vocabulary:
            return True
        if len(w) >= 6 and any(len(v) >= 6 and difflib.SequenceMatcher(None, w, v).ratio() >= 0.8
                               for v in vocabulary):
            return True
    return False


def _unglue(tokens, known):
    """Whisper glues the article to the name: "racoro" (a coro), "reprecoro" (ir a
    precoro), "alcoro". A word that ends with a section word is that word."""
    out = []
    for w in tokens:
        if w not in known:
            tails = [k for k in known if len(k) >= 4 and w.endswith(k)]
            if tails:
                w = max(tails, key=len)
        out.append(w)
    return out


def find_section(tokens, sections):
    """The section named in `tokens`: an exact name ("Verso 2") beats the bare word
    ("Coro", which the bridge resolves to the next "Coro 1"/"Coro 2")."""
    known = {w for name in sections for w in _section_tokens(name) if not w.isdigit()}
    tokens = _unglue(tokens, known)
    best = None
    for name in sections:
        full = _section_tokens(name)
        numbered = len(full) > 1 and full[-1].isdigit()
        base = full[:-1] if numbered else full
        bare = re.sub(r"\s+\d+$", "", name.strip()) if numbered else name
        for seq, value in ((full, name), (base, bare)):
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
    """(description, [commands]) or None. No commands: understood, but not possible here.

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

    if _has(tokens, CANCEL):
        return "Cancelar", [{"cmd": "cancel"}]
    if tokens[0] in STOP:
        return "Parar", [{"cmd": "stop"}]

    if _has(tokens, SONG) or ("next" in words and "song" in words):
        if _has(tokens, NEXT):
            return "Siguiente canción", [{"cmd": "next_song"}]
        n = _number(tokens)
        if n is not None:
            return "Canción %d" % n, [{"cmd": "song", "number": n}]
    for number, title in songs:
        if len(normalize(title)) >= 2 and _contains(tokens, normalize(title)[:2]):
            return "Canción %d · %s" % (number, title), [{"cmd": "song", "number": number}]

    if _has(tokens, MUTE | UNMUTE):
        track = find_track(tokens, tracks)
        if track:
            mute = bool(_has(tokens, MUTE))
            return ("Silenciar " if mute else "Activar ") + track, [{"cmd": "mute", "track": track, "on": mute}]

    section = find_section(tokens, sections)
    repeat = bool(_has(tokens, REPEAT)) or _contains(tokens, ["otra", "vez"]) or _contains(tokens, ["de", "nuevo"]) \
        or _contains(tokens, ["vez", "mas"])
    if repeat and (section is None or _same_section(section, current)):
        return "Repetir" + (" " + current if current else ""), [{"cmd": "repeat"}]
    if section is None:
        missing = [GENERIC_SECTIONS[w] for w in _unglue(tokens, set(GENERIC_SECTIONS)) if w in GENERIC_SECTIONS]
        if missing and sections:
            return "Esta canción no tiene %s" % missing[0], []
    if section:
        shown = section[:1].upper() + section[1:]
        if _has(tokens, PLAY):
            return "Desde " + shown, [{"cmd": "goto", "section": section}, {"cmd": "play"}]
        return "Ir a " + shown, [{"cmd": "goto", "section": section}]
    if _has(tokens, RELEASE):
        return "Seguir", [{"cmd": "release"}]
    if _has(tokens, NEXT):
        return "Siguiente sección", [{"cmd": "next_section"}]
    if _has(tokens, PLAY):
        return "Play", [{"cmd": "play"}]
    return None


def _same_section(spoken, current):
    if not current:
        return True
    a, b = _section_tokens(spoken), _section_tokens(current)
    return a == b or a == b[:len(a)]
