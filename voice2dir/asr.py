"""ASR layer: audio file -> transcript, via whisper-cli (whisper.cpp).

Audio in any format ffmpeg can decode (.ogg, .mp3, .wav, .flac, ...)
is first converted to 16 kHz mono PCM. The ggml model is downloaded
from the whisper.cpp Hugging Face repository on first use.

External tools: ffmpeg, whisper-cli. Both come from nixpkgs; the
devShell in flake.nix provides them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(
    os.environ.get("VOICE2DIR_MODELS_DIR", Path.home() / ".cache" / "voice2dir" / "models")
)
DEFAULT_MODEL = os.environ.get("VOICE2DIR_MODEL", "ggml-small-q5_1.bin")
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

KNOWN_MODELS = [
    "ggml-tiny.bin", "ggml-tiny-q5_1.bin",
    "ggml-base.bin", "ggml-base-q5_1.bin",
    "ggml-small.bin", "ggml-small-q5_1.bin",
    "ggml-medium.bin", "ggml-medium-q5_1.bin",
]


class AsrError(Exception):
    pass


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise AsrError(
            f"не найден {name!r}. Запустите окружение: nix develop "
            f"(или установите {name} в PATH)"
        )
    return path


def ensure_model(name: str = DEFAULT_MODEL) -> Path:
    """Return the path to a ggml model, downloading it if necessary."""
    path = MODELS_DIR / name
    if path.is_file():
        return path
    if name not in KNOWN_MODELS and not name.startswith("ggml-"):
        # A bare path to an already-existing model file is also fine.
        candidate = Path(name)
        if candidate.is_file():
            return candidate
        raise AsrError(f"неизвестная модель {name!r}; известные: {', '.join(KNOWN_MODELS)}")
    url = MODEL_URL + name
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    print(f"voice2dir: загружаю модель {name} ...", file=sys.stderr)
    try:
        with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done // total
                    print(f"\r  {done >> 20} / {total >> 20} MiB ({pct}%)", end="", file=sys.stderr)
        print(file=sys.stderr)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise AsrError(f"не удалось скачать модель {url}: {e}") from e
    tmp.rename(path)
    return path


def to_wav16k(audio: Path, out_dir: Path) -> Path:
    """Convert any decodable audio into 16 kHz mono PCM WAV."""
    ffmpeg = _require_tool("ffmpeg")
    wav = out_dir / (audio.stem + ".16k.wav")
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(audio), "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le", str(wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AsrError(f"ffmpeg не смог декодировать {audio}: {proc.stderr.strip()}")
    return wav


# Initial prompt for whisper: biases the decoder towards the DSL
# vocabulary. Newlines in the prompt encourage line-per-command output.
# Domain-biased decoding is the difference between "конец файла" and
# "канец яйма" on a noisy channel.
DSL_PROMPT = "каталог тест\nфайл а\nтекст\nконец файла\nконец каталога\nконец дерева\nвверх\nссылка а на б\nскрипт с\n"


def transcribe_file(audio: Path, lang: str = "ru", model: str = DEFAULT_MODEL,
                    workdir: Path | None = None) -> str:
    """Audio file (ogg/mp3/wav/...) -> transcript text."""
    whisper = _require_tool("whisper-cli")
    model_path = ensure_model(model)
    work = workdir or audio.parent
    wav = to_wav16k(audio, work)
    out_prefix = work / (audio.stem + ".asr")
    cmd = [
        whisper, "-m", str(model_path), "-f", str(wav),
        "-l", lang, "-otxt", "-of", str(out_prefix), "-np",
        "--prompt", DSL_PROMPT, "-bs", "5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    txt = Path(str(out_prefix) + ".txt")
    if proc.returncode != 0 or not txt.is_file():
        raise AsrError(f"whisper-cli завершился с ошибкой: {proc.stderr.strip()[:500]}")
    try:
        return txt.read_text(encoding="utf-8")
    finally:
        txt.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)
