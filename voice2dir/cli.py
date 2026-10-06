"""voice2dir: narrate a directory tree, get it on disk.

Pipeline: voice -> ASR -> transcript -> DSL -> JSON -> tree (json2dir
scheme) -> read-back verification.

Exit codes (same canon as dir2json):
    0 - success (tree built and verified)
    1 - error (ASR, DSL, I/O)
    2 - usage error
    3 - read-back verification failed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import asr, dsl, materialize, record

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_DRIFT = 0, 1, 2, 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice2dir",
        description="Наговори дерево каталогов — получи его на диске (схема json2dir).",
    )
    p.add_argument("-V", "--version", action="version",
                   version=f"voice2dir {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--json", action="store_true",
                        help="вывести JSON-дерево вместо записи на диск")
        sp.add_argument("--dry-run", action="store_true",
                        help="показать, что будет создано, не трогая диск")
        sp.add_argument("--lenient", action="store_true",
                        help="пропускать нераспознанные строки транскрипта с предупреждением")
        sp.add_argument("--no-verify", action="store_true",
                        help="не выполнять обратную проверку (read-back)")

    sp = sub.add_parser("audio", help="аудиофайл (.ogg/.mp3/.wav/...) -> дерево")
    sp.add_argument("audio", type=Path, help="входной аудиофайл")
    sp.add_argument("out", nargs="?", type=Path, default=Path("."),
                    help="целевой каталог [по умолчанию: .]")
    sp.add_argument("--lang", default="ru", help="язык записи [ru]")
    sp.add_argument("--model", default=asr.DEFAULT_MODEL,
                    help=f"ggml-модель [по умолчанию: {asr.DEFAULT_MODEL}]")
    add_common(sp)

    sp = sub.add_parser("record", help="запись с микрофона (Ctrl+C — стоп) -> дерево")
    sp.add_argument("out", nargs="?", type=Path, default=Path("."),
                    help="целевой каталог [по умолчанию: .]")
    sp.add_argument("--lang", default="ru", help="язык записи [ru]")
    sp.add_argument("--model", default=asr.DEFAULT_MODEL,
                    help=f"ggml-модель [по умолчанию: {asr.DEFAULT_MODEL}]")
    add_common(sp)

    sp = sub.add_parser("transcribe", help="аудиофайл -> транскрипт (без построения)")
    sp.add_argument("audio", type=Path, help="входной аудиофайл")
    sp.add_argument("--lang", default="ru", help="язык записи [ru]")
    sp.add_argument("--model", default=asr.DEFAULT_MODEL,
                    help=f"ggml-модель [по умолчанию: {asr.DEFAULT_MODEL}]")

    sp = sub.add_parser("build", help="текстовый транскрипт -> дерево (без ASR)")
    sp.add_argument("transcript", type=Path, help="файл транскрипта (или - для stdin)")
    sp.add_argument("out", nargs="?", type=Path, default=Path("."),
                    help="целевой каталог [по умолчанию: .]")
    add_common(sp)

    return p


def _emit_tree(tree: dict, out: Path, args) -> int:
    if args.json:
        print(json.dumps(tree, ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.dry_run:
        for path in materialize.materialize(tree, out, dry_run=True):
            print(f"создать: {path}")
        return EXIT_OK
    materialize.materialize(tree, out)
    if args.no_verify:
        print(f"voice2dir: дерево записано в {out}", file=sys.stderr)
        return EXIT_OK
    if not materialize.verify(tree, out):
        print("voice2dir: обратная проверка не сошлась (дрейф)", file=sys.stderr)
        return EXIT_DRIFT
    print(f"voice2dir: дерево записано в {out} и проверено обратным чтением", file=sys.stderr)
    return EXIT_OK


def _from_transcript(text: str, args) -> int:
    try:
        tree = dsl.parse(text, lenient=getattr(args, "lenient", False))
    except dsl.DslError as e:
        print(f"voice2dir: транскрипт не разобран: {e}", file=sys.stderr)
        return EXIT_ERROR
    return _emit_tree(tree, args.out, args)


def cmd_audio(args) -> int:
    if not args.audio.is_file():
        print(f"voice2dir: файл не найден: {args.audio}", file=sys.stderr)
        return EXIT_ERROR
    try:
        text = asr.transcribe_file(args.audio, lang=args.lang, model=args.model)
    except (asr.AsrError, OSError) as e:
        print(f"voice2dir: {e}", file=sys.stderr)
        return EXIT_ERROR
    print("voice2dir: --- транскрипт ---", file=sys.stderr)
    print(text.strip(), file=sys.stderr)
    print("voice2dir: ---------------------", file=sys.stderr)
    return _from_transcript(text, args)


def cmd_record(args) -> int:
    try:
        wav = Path.home() / ".cache" / "voice2dir" / "recording.wav"
        record.record_wav(wav)
        text = asr.transcribe_file(wav, lang=args.lang, model=args.model)
    except (asr.AsrError, OSError) as e:
        print(f"voice2dir: {e}", file=sys.stderr)
        return EXIT_ERROR
    print("voice2dir: --- транскрипт ---", file=sys.stderr)
    print(text.strip(), file=sys.stderr)
    print("voice2dir: ---------------------", file=sys.stderr)
    return _from_transcript(text, args)


def cmd_transcribe(args) -> int:
    if not args.audio.is_file():
        print(f"voice2dir: файл не найден: {args.audio}", file=sys.stderr)
        return EXIT_ERROR
    try:
        text = asr.transcribe_file(args.audio, lang=args.lang, model=args.model)
    except (asr.AsrError, OSError) as e:
        print(f"voice2dir: {e}", file=sys.stderr)
        return EXIT_ERROR
    print(text.strip())
    return EXIT_OK


def cmd_build(args) -> int:
    if str(args.transcript) == "-":
        return _from_transcript(sys.stdin.read(), args)
    if not args.transcript.is_file():
        print(f"voice2dir: файл не найден: {args.transcript}", file=sys.stderr)
        return EXIT_ERROR
    return _from_transcript(args.transcript.read_text(encoding="utf-8"), args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "audio": cmd_audio,
        "record": cmd_record,
        "transcribe": cmd_transcribe,
        "build": cmd_build,
    }
    try:
        return handlers[args.command](args)
    except materialize.MaterializeError as e:
        print(f"voice2dir: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("voice2dir: прервано", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
