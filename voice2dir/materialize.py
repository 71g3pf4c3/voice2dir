"""Materialize a json2dir-scheme JSON object as a directory tree, and
read it back for verification (dir2json semantics).

Scheme (RFC J2D-1):
    object          -> directory
    string          -> regular file with exactly that content
    ["link", t]     -> symlink to t
    ["script", c]   -> file with the executable bit set
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


class MaterializeError(Exception):
    pass


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise MaterializeError(f"пустое имя записи: {name!r}")
    if "/" in name:
        raise MaterializeError(f"имя {name!r} содержит '/' — используйте вложенные объекты")
    if name in (".", ".."):
        raise MaterializeError(f"имя {name!r} зарезервировано")


def _check_value(name: str, value) -> None:
    if isinstance(value, (str, dict)):
        return
    if (
        isinstance(value, list)
        and len(value) == 2
        and value[0] in ("link", "script")
        and isinstance(value[1], str)
    ):
        return
    raise MaterializeError(
        f"запись {name!r}: недопустимое значение {value!r} — ожидается строка, объект, "
        "['link', цель] или ['script', содержимое]"
    )


def _remove(path: Path) -> None:
    """json2dir semantics: delete whatever occupies the target first."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        import shutil
        shutil.rmtree(path)


def materialize(tree: dict, out_dir: Path, dry_run: bool = False) -> list[Path]:
    """Create the tree under out_dir. Returns the list of created paths."""
    if not isinstance(tree, dict):
        raise MaterializeError("корень дерева обязан быть объектом")

    created: list[Path] = []
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    _materialize_dir(tree, out_dir, dry_run, created)
    return created


def _materialize_dir(tree: dict, dir_path: Path, dry_run: bool, created: list[Path]) -> None:
    for name, value in sorted(tree.items()):
        _check_name(name)
        _check_value(name, value)
        path = dir_path / name
        if dry_run:
            created.append(path)
            if isinstance(value, dict):
                _materialize_dir(value, path, dry_run, created)
            continue
        _remove(path)
        if isinstance(value, dict):
            path.mkdir()
            _materialize_dir(value, path, dry_run, created)
        elif isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            tag, arg = value
            if tag == "link":
                os.symlink(arg, path)
            else:  # script
                path.write_text(arg, encoding="utf-8")
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        created.append(path)


# --- read-back (dir2json semantics) ---------------------------------------

def read_back(root: Path) -> dict:
    """Walk the tree back into a JSON object, dir2json-style: sorted
    entries, symlinks never followed, special files rejected."""
    result: dict = {}
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        meta = entry.lstat()
        mode = meta.st_mode
        if stat.S_ISLNK(mode):
            result[entry.name] = ["link", os.readlink(entry)]
        elif stat.S_ISDIR(mode):
            result[entry.name] = read_back(entry)
        elif stat.S_ISREG(mode):
            content = entry.read_text(encoding="utf-8")
            if mode & 0o111:
                result[entry.name] = ["script", content]
            else:
                result[entry.name] = content
        else:
            raise MaterializeError(f"{entry}: специальный файл не может быть прочитан обратно")
    return result


def diff_trees(desired: dict, actual: dict, prefix: str = "") -> list[str]:
    """Human-readable mismatch list between desired and observed trees."""
    mismatches: list[str] = []
    for name in sorted(set(desired) | set(actual)):
        path = f"{prefix}/{name}" if prefix else name
        d, a = desired.get(name), actual.get(name)
        if d == a:
            continue
        if d is None:
            mismatches.append(f"{path}: не содержится в желаемом дереве")
        elif a is None:
            mismatches.append(f"{path}: отсутствует на диске")
        else:
            mismatches.append(f"{path}: ожидалось {d!r}, получено {a!r}")
    return mismatches


def verify(tree: dict, out_dir: Path) -> bool:
    """Read the tree back and compare with the intent. Prints a report on
    mismatch. Returns True when the roundtrip is exact."""
    actual = read_back(out_dir)
    mismatches = diff_trees(tree, actual)
    if mismatches:
        for m in mismatches:
            print(f"voice2dir: расхождение: {m}", file=sys.stderr)
        return False
    return True
