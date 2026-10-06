"""Deterministic transcript -> JSON parser for the voice2dir DSL.

The DSL is line-based and designed for speech: one command per spoken
line, no punctuation required. Keywords are matched case-insensitively;
file names and content keep their original case.

Grammar (Russian):

    каталог <имя>          - create and enter a directory
    файл <имя>             - begin a regular file; the following lines are
                             its content until "конец файла"
    скрипт <имя>           - begin an executable file; same content block
    ссылка <имя> на <цель> - create a symbolic link
    вверх | конец каталога  - leave the current directory
    конец дерева           - stop; the rest of the transcript is ignored

Content lines are joined with a newline, each file gets a trailing
newline (an empty content block produces an empty file).
"""

from __future__ import annotations

DIR = "каталог"
FILE = "файл"
SCRIPT = "скрипт"
LINK = "ссылка"
UP = "вверх"
END_DIR = "конец каталога"
END_FILE = "конец файла"
END_TREE = "конец дерева"
LINK_SEP = " на "

# Tags of the json2dir scheme (English, as in RFC J2D-1).
TAG_LINK = "link"
TAG_SCRIPT = "script"


class DslError(Exception):
    """Raised when a transcript violates the DSL."""

    def __init__(self, lineno: int, message: str):
        self.lineno = lineno
        super().__init__(f"строка {lineno}: {message}")


def _validate_name(lineno: int, name: str) -> str:
    name = name.strip()
    if not name:
        raise DslError(lineno, "пустое имя записи")
    if " " in name:
        # One spoken word per name: a multi-word name almost always means
        # that ASR glued two commands into one line.
        raise DslError(
            lineno,
            f"имя {name!r} содержит пробелы — имя произносится одним словом "
            "(склеивание строк от распознавания?)",
        )
    if "/" in name:
        raise DslError(lineno, f"имя {name!r} содержит '/' — вложенность задаётся словом «каталог»")
    if name in (".", ".."):
        raise DslError(lineno, f"имя {name!r} зарезервировано")
    return name


def parse(transcript: str, lenient: bool = False) -> dict:
    """Parse a transcript into a json2dir-scheme JSON object.

    With ``lenient=True``, unknown top-level lines are skipped with a
    warning on stderr instead of raising (useful for noisy ASR output).
    """
    root: dict = {}
    stack: list[dict] = [root]
    # Content mode: (kind, name, lines) while inside a file/script block.
    content_mode: tuple[str, str, list[str]] | None = None

    for lineno, raw in enumerate(transcript.splitlines(), 1):
        line = raw.strip()
        keyword = line.casefold()

        if content_mode is not None:
            kind, name, lines = content_mode
            if keyword == END_FILE:
                text = "\n".join(lines)
                if lines:
                    text += "\n"
                stack[-1][name] = text if kind == FILE else [TAG_SCRIPT, text]
                content_mode = None
            else:
                # Content is kept verbatim, only trailing spaces dropped.
                lines.append(raw.rstrip())
            continue

        if not line:
            continue

        if keyword == UP or keyword == END_DIR:
            if len(stack) == 1:
                raise DslError(lineno, "«вверх» на верхнем уровне дерева")
            stack.pop()
            continue

        if keyword == END_TREE:
            break

        low = keyword
        if low.startswith(DIR + " "):
            name = _validate_name(lineno, line[len(DIR) + 1:])
            stack[-1][name] = {}
            stack.append(stack[-1][name])
        elif low.startswith(FILE + " ") or low.startswith(SCRIPT + " "):
            kind = FILE if low.startswith(FILE + " ") else SCRIPT
            name = _validate_name(lineno, line[len(kind) + 1:])
            content_mode = (kind, name, [])
        elif low.startswith(LINK + " "):
            rest = line[len(LINK) + 1:]
            if LINK_SEP not in rest:
                raise DslError(lineno, "ссылка без цели: ожидается «ссылка <имя> на <цель>»")
            name, _, target = rest.partition(LINK_SEP)
            name = _validate_name(lineno, name)
            target = target.strip()
            if not target:
                raise DslError(lineno, "пустая цель ссылки")
            stack[-1][name] = ["link", target]
        else:
            if lenient:
                import sys
                print(f"voice2dir: предупреждение: строка {lineno} пропущена: {line!r}", file=sys.stderr)
                continue
            raise DslError(lineno, f"не распознана команда: {line!r}")

    if content_mode is not None:
        raise DslError(
            len(transcript.splitlines()),
            f"файл {content_mode[1]!r} не закрыт (нет «{END_FILE}»)",
        )

    return root
