"""Spoken JSON: normalize a transcript where punctuation was dictated as
words ("кавычка", "фигурная скобка", "двоеточие") into actual JSON text,
then parse it.

Example dictation:

    фигурная скобка кавычка приветствие кавычка двоеточие
    кавычка привет мир кавычка закрывающая фигурная скобка

normalizes to:

    { "приветствие": "привет мир" }

Bracket direction: explicit forms ("открывающая/закрывающая фигурная
скобка", "открой/закрой фигурную скобку", "левая/правая") always win.
The bare "фигурная скобка" / "квадратная скобка" are resolved by parser
state: a bracket after a completed value closes, a bracket where a
value is expected opens. Well-formed dictation needs no direction words.

Punctuation words are reserved: "запятая" always means ',', "точка"
means '.', even inside string content (that is how dictated prose gets
its commas). The escape is "бэкслэш" (e.g. "бэкслэш кавычка" for a
literal quote inside a string). "перевод строки" inside a string
becomes a newline in the file content.
"""

from __future__ import annotations

import json

from . import materialize

# Actions
_QUOTE = "quote"
_OPEN_CURLY = "open_curly"
_CLOSE_CURLY = "close_curly"
_SMART_CURLY = "smart_curly"
_OPEN_SQUARE = "open_square"
_CLOSE_SQUARE = "close_square"
_SMART_SQUARE = "smart_square"
_COLON = "colon"
_COMMA = "comma"
_DOT = "dot"
_NEWLINE = "newline"
_BACKSLASH = "backslash"

# Longest phrases must be tried first (see _match).
PHRASES: dict[tuple[str, ...], str] = {
    # --- quotes --------------------------------------------------------
    ("двойная", "кавычка"): _QUOTE,
    ("открывающая", "кавычка"): _QUOTE,
    ("закрывающая", "кавычка"): _QUOTE,
    ("кавычка",): _QUOTE,
    ("кавычки",): _QUOTE,
    ("кавычку",): _QUOTE,
    # --- explicit curly braces ----------------------------------------
    ("открывающая", "фигурная", "скобка"): _OPEN_CURLY,
    ("открывающая", "фигурную", "скобку"): _OPEN_CURLY,
    ("открывающую", "фигурную", "скобку"): _OPEN_CURLY,
    ("открой", "фигурную", "скобку"): _OPEN_CURLY,
    ("открыть", "фигурную", "скобку"): _OPEN_CURLY,
    ("левая", "фигурная", "скобка"): _OPEN_CURLY,
    ("закрывающая", "фигурная", "скобка"): _CLOSE_CURLY,
    ("закрывающая", "фигурную", "скобку"): _CLOSE_CURLY,
    ("закрывающую", "фигурную", "скобку"): _CLOSE_CURLY,
    ("закрой", "фигурную", "скобку"): _CLOSE_CURLY,
    ("закрыть", "фигурную", "скобку"): _CLOSE_CURLY,
    ("правая", "фигурная", "скобка"): _CLOSE_CURLY,
    # --- explicit square brackets --------------------------------------
    ("открывающая", "квадратная", "скобка"): _OPEN_SQUARE,
    ("открывающая", "квадратную", "скобку"): _OPEN_SQUARE,
    ("открывающую", "квадратную", "скобку"): _OPEN_SQUARE,
    ("открой", "квадратную", "скобку"): _OPEN_SQUARE,
    ("открыть", "квадратную", "скобку"): _OPEN_SQUARE,
    ("левая", "квадратная", "скобка"): _OPEN_SQUARE,
    ("закрывающая", "квадратная", "скобка"): _CLOSE_SQUARE,
    ("закрывающая", "квадратную", "скобку"): _CLOSE_SQUARE,
    ("закрывающую", "квадратную", "скобку"): _CLOSE_SQUARE,
    ("закрой", "квадратную", "скобку"): _CLOSE_SQUARE,
    ("закрыть", "квадратную", "скобку"): _CLOSE_SQUARE,
    ("правая", "квадратная", "скобка"): _CLOSE_SQUARE,
    # --- bare brackets: direction decided by parser state ---------------
    ("фигурная", "скобка"): _SMART_CURLY,
    ("фигурную", "скобку"): _SMART_CURLY,
    ("квадратная", "скобка"): _SMART_SQUARE,
    ("квадратную", "скобку"): _SMART_SQUARE,
    # --- the rest -------------------------------------------------------
    ("двоеточие",): _COLON,
    ("запятая",): _COMMA,
    ("запятую",): _COMMA,
    ("точка",): _DOT,
    ("перевод", "строки"): _NEWLINE,
    ("новая", "строка"): _NEWLINE,
    ("обратный", "слеш"): _BACKSLASH,
    ("обратный", "слэш"): _BACKSLASH,
    ("бэкслэш",): _BACKSLASH,
    ("бэкслеш",): _BACKSLASH,
}

_MAX_PHRASE = 3

# After these characters the next word attaches without a space.
_NO_SPACE_AFTER = {'"', "\\"}


class SpokenJsonError(Exception):
    pass


def _match(words: list[str], i: int) -> tuple[int, str] | None:
    for length in (_MAX_PHRASE, 2, 1):
        if i + length > len(words):
            continue
        key = tuple(w.casefold() for w in words[i:i + length])
        action = PHRASES.get(key)
        if action is not None:
            return length, action
    return None


def normalize(transcript: str) -> str:
    """Rewrite dictated punctuation words into JSON punctuation."""
    words = transcript.split()
    out: list[str] = []
    in_string = False
    # Last structural token emitted outside of strings:
    #   None (start) | '{' | '[' | '}' | ']' | ':' | ',' | '"' | 'w' (word)
    last_struct: str | None = None

    def add_punct(ch: str) -> None:
        out.append(ch)

    def add_word(word: str) -> None:
        if out and out[-1] and out[-1][-1] not in (" ",) and (
            out[-1][-1] in _NO_SPACE_AFTER
            or (out[-1][-1] == "." and word[:1].isdigit())
        ):
            out.append(word)
        elif out:
            out.append(" ")
            out.append(word)
        else:
            out.append(word)

    i = 0
    while i < len(words):
        matched = _match(words, i)
        if matched is None:
            add_word(words[i])
            if not in_string:
                last_struct = "w"
            i += 1
            continue

        length, action = matched
        i += length

        if action == _QUOTE:
            add_punct('"')
            in_string = not in_string
            if not in_string:
                last_struct = '"'
            continue

        if action == _OPEN_CURLY:
            add_punct("{")
            last_struct = "{"
        elif action == _CLOSE_CURLY:
            add_punct("}")
            last_struct = "}"
        elif action == _OPEN_SQUARE:
            add_punct("[")
            last_struct = "["
        elif action == _CLOSE_SQUARE:
            add_punct("]")
            last_struct = "]"
        elif action in (_SMART_CURLY, _SMART_SQUARE):
            if in_string:
                # Inside string content a bare bracket word means the
                # opening character; be explicit for the closing one.
                add_punct("{" if action == _SMART_CURLY else "[")
                continue
            expect_value = last_struct in (None, "{", "[", ",", ":")
            if action == _SMART_CURLY:
                add_punct("{" if expect_value else "}")
                last_struct = "{" if expect_value else "}"
            else:
                add_punct("[" if expect_value else "]")
                last_struct = "[" if expect_value else "]"
        elif action == _COLON:
            add_punct(":")
            if not in_string:
                last_struct = ":"
        elif action == _COMMA:
            add_punct(",")
            if not in_string:
                last_struct = ","
        elif action == _DOT:
            add_punct(".")
        elif action == _NEWLINE:
            # Inside a string this is the two-character escape \n;
            # outside a string it is a dictation error caught by json.
            out.append("\\n")
        elif action == _BACKSLASH:
            out.append("\\")

    return "".join(out).strip()


def parse(transcript: str) -> dict:
    """Transcript with spoken punctuation -> validated scheme tree."""
    normalized = normalize(transcript)
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as e:
        raise SpokenJsonError(
            f"нормализованный JSON некорректен ({e.msg}, позиция {e.pos}): "
            f"{normalized!r}"
        ) from e
    if not isinstance(value, dict):
        raise SpokenJsonError(
            f"корень обязан быть объектом, получено: {type(value).__name__}"
        )
    materialize.validate(value)
    return value
