"""What the director said -> SonarStage Link commands.

Closed vocabulary in Spanish (and the usual English words), after a wake word:

    "Secuencia, repetimos el coro"      repeat it once (or go to the chorus if we are elsewhere)
    "Secuencia, en bucle"               repeat until "seguimos"
    "Secuencia, vamos al puente"        go to the next "Puente" at the end of this section
    "Secuencia, siguiente"              next section
    "Secuencia, seguimos"               release a repeat
    "Secuencia, cancela"                forget the pending jump
    "Secuencia, siguiente canción"      next song (stopped, ready to play)
    "Secuencia, canción tres"           song 3
    "Secuencia, después va la canción tres"   song 3 comes next (the show remembers the order)
    "Secuencia, saltamos la canción dos"      leave song 2 out
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
PREVIOUS = {"anterior", "previous", "pasada", "atras"}
AFTER = {"despues", "luego", "continuacion", "enseguida", "after"}
SKIP = {"saltamos", "saltar", "salta", "omitimos", "omite", "omitir", "quitamos", "quita", "sacamos", "saca"}
LAST = {"ultima", "ultimo", "last"}
SONG = {"cancion", "song", "tema"}
# Mute and unmute change what the audience hears: exact words only, never "close enough"
# ("desactivar" is 82 % like "activar"). Both kinds in one phrase -> refused.
MUTE = {"silencia", "silenciar", "silenciamos", "mutea", "mutear", "muteamos", "motear", "apaga",
        "apagar", "apagamos", "quita", "quitar", "quitamos", "saca", "sacar", "calla", "mute",
        "desactiva", "desactivar", "desactivamos", "desactivame", "desactivo", "desactivada",
        "silencio", "silenci", "silenciala", "apagala", "quitala"}
UNMUTE = {"activa", "activar", "activamos", "activo", "activala", "prende", "prender", "enciende", "desmutea", "pon",
          "suena", "unmute", "devuelve", "regresa"}
HOLD = {"bucle", "loop", "mantenemos", "manten", "mantener", "mantengamos", "congela", "hold"}
REPEAT = {"repite", "repetimos", "repetir", "repitan", "repeat", "again"}
RELEASE = {"seguimos", "sigue", "suelta", "soltamos", "continua", "continuamos", "continue",
           "avanza", "avanzamos", "salimos", "release"}
PLAY = {"dale", "dali", "play", "arranca", "arrancamos", "empieza", "empezamos", "comienza", "comenzamos",
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


def after_wake_word(tokens, wake_words=WAKE_WORDS, within=None):
    """Tokens after the (last) wake word, or None if it was not said. Directors talk to the
    band first: "Banda, vamos al coro. Secuencia, vamos al coro". Whisper sometimes splits
    it ("Se cuesta"), so two words together also count. `within` limits it to the first words."""
    last = None
    for i in range(len(tokens) if within is None else min(within, len(tokens))):
        if _is_wake(tokens[i], wake_words):
            last = i
        elif i + 1 < len(tokens) and _is_wake(tokens[i] + tokens[i + 1], wake_words, 0.7):
            last = i + 1
    return None if last is None else tokens[last + 1:]


def wake_rest(text, wake_words=WAKE_WORDS):
    """What follows the wake word ("" if nothing), or None if the phrase does not open with it."""
    rest = after_wake_word(normalize(text), wake_words)
    return None if rest is None else " ".join(rest)


def is_wake_only(text, wake_words=WAKE_WORDS):
    """Just "Secuencia": the order comes in the next phrase (people pause after it)."""
    return wake_rest(text, wake_words) == ""


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
    """The track named: exact words first, then close ones ("botería" for "batería"). The
    verb (mute/unmute) is never guessed; the track can be, among a handful of names, as
    long as only one of them is close."""
    names = []
    for name in tracks:
        words = set(_section_tokens(name))
        spoken = set()
        for key, aliases in TRACK_WORDS.items():
            if key in words:
                spoken.update(aliases)
        spoken.update(w for w in words if len(w) >= 4)
        names.append((name, spoken))
    for name, spoken in names:
        if spoken & set(tokens):
            return name
    close = [name for name, spoken in names
             if any(len(w) >= 5 and len(a) >= 5 and difflib.SequenceMatcher(None, w, a).ratio() >= 0.75
                    for w in tokens for a in spoken)]
    return close[0] if len(close) == 1 else None


FILLER = {"al", "a", "la", "el", "ir", "vamos", "de", "del", "desde", "con", "en", "y", "por", "favor",
          "otra", "vez", "mas", "nuevo", "seccion", "parte", "ahora", "ya", "las", "los", "un", "le", "lo",
          "porfa", "banda", "hasta", "todo", "todos", "esto", "eso", "va", "es", "sigue"}


def _vocabulary(sections, tracks, songs):
    words = set(FILLER) | set(SECTION_WORDS.values()) | set(GENERIC_SECTIONS)
    for group in (CANCEL, STOP, NEXT, PREVIOUS, LAST, SONG, MUTE, UNMUTE, HOLD, REPEAT, RELEASE, PLAY, AFTER, SKIP):
        words |= group
    for aliases in TRACK_WORDS.values():
        words |= set(aliases)
    for name in list(sections) + list(tracks) + [t for _, t in songs]:
        words |= set(normalize(name))
    return words


def looks_like_an_order(tokens, sections=(), tracks=(), songs=()):
    """Half or more of the words belong to the orders' vocabulary (close ones count): a
    sung line after a "Secuencia" Whisper imagined over the music does not."""
    if not tokens:
        return False
    vocab = _vocabulary(sections, tracks, songs)
    known = sum(1 for w in tokens if w in vocab or w.isdigit()
                or any(len(v) >= 4 and w.endswith(v) for v in vocab)             # "alcoro"
                or (len(w) >= 5 and any(len(v) >= 5 and _like(w, v) for v in vocab)))
    return known * 2 >= len(tokens)


def _number(tokens):
    return next((int(w) for w in tokens if w.isdigit()), None)


def parse(text, sections=(), tracks=(), songs=(), current=None, wake_words=WAKE_WORDS, song_number=None):
    """(description, [commands]) or None. No commands: understood, but not possible here.

    sections: names in the current song; tracks: muteable tracks; songs: [(number, title)];
    current: name of the section playing; song_number: the song we are in.
    wake_words=() means no wake word is needed.
    """
    tokens = normalize(text)
    if wake_words:
        tokens = after_wake_word(tokens, wake_words)
        if not tokens:
            return None
    if not tokens or not looks_like_an_order(tokens, sections, tracks, songs):
        return None
    words = set(tokens)

    if _has(tokens, CANCEL):
        return "Cancelar", [{"cmd": "cancel"}]
    if tokens[0] in STOP:
        return "Parar", [{"cmd": "stop"}]

    song = _song_order(tokens, words, songs, song_number)
    if song is not None:
        return song

    if words & (MUTE | UNMUTE):
        track = find_track(tokens, tracks)
        if track:
            if words & MUTE and words & UNMUTE:
                return "No entendí si activar o silenciar %s" % track, []
            mute = bool(words & MUTE)
            return ("Silenciar " if mute else "Activar ") + track, [{"cmd": "mute", "track": track, "on": mute}]
    elif _has(tokens, MUTE | UNMUTE) and find_track(tokens, tracks):
        return "No entendí si activar o silenciar", []          # a near miss on a mute verb

    if words & HOLD:
        return "Repetir hasta «seguimos»", [{"cmd": "hold"}]
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


def _song_order(tokens, words, songs, song_number):
    """Orders about songs: jump to one now, or change what comes after this one."""
    said_song = _has(tokens, SONG) or ("next" in words and "song" in words)
    target = None
    if said_song and _number(tokens) is not None:
        target = _number(tokens)
    for number, title in songs:
        if target is None and len(normalize(title)) >= 2 and _contains(tokens, normalize(title)[:2]):
            target = number
    if target is None and said_song and _has(tokens, LAST) and songs:
        target = songs[-1][0]
    titles = dict(songs)
    shown = ("Canción %d · %s" % (target, titles[target])) if target in titles else "Canción %s" % target

    if target is not None and words & SKIP:
        return "Saltar " + shown.lower(), [{"cmd": "skip", "number": target}]
    if target is not None and (words & AFTER or _has(tokens, NEXT)):
        return "Después: " + shown.lower(), [{"cmd": "next_is", "number": target}]
    if said_song and _has(tokens, NEXT):
        return "Siguiente canción", [{"cmd": "next_song"}]
    if said_song and _has(tokens, PREVIOUS):
        if song_number and song_number > 1:
            return "Canción anterior", [{"cmd": "song", "number": song_number - 1}]
        return "Ya es la primera canción", []
    if target is None:
        return None
    if _has(tokens, PLAY):                          # "empezamos con la primera canción"
        return shown + " y play", [{"cmd": "song", "number": target}, {"cmd": "play"}]
    return shown, [{"cmd": "song", "number": target}]


def _same_section(spoken, current):
    if not current:
        return True
    a, b = _section_tokens(spoken), _section_tokens(current)
    return a == b or a == b[:len(a)]
