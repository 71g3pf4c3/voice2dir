"""Live microphone recording via ffmpeg.

Records from the default audio source into a WAV file until the user
presses Ctrl+C. ffmpeg handles SIGINT by finalizing the file cleanly,
so the recording is complete up to the moment of interruption.

Source auto-detection: PulseAudio (``-f pulse -i default``) first, then
ALSA (``-f alsa -i default``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .asr import _require_tool, AsrError


def record_wav(out: Path) -> Path:
    """Record from the microphone into ``out`` (WAV). Ctrl+C stops."""
    ffmpeg = _require_tool("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)

    formats = [
        ["-f", "pulse", "-i", "default"],
        ["-f", "alsa", "-i", "default"],
    ]
    last_err = ""
    for source in formats:
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               *source, "-ar", "16000", "-ac", "1",
               "-c:a", "pcm_s16le", str(out)]
        print("voice2dir: запись... Ctrl+C — остановить", file=sys.stderr)
        try:
            proc = subprocess.run(cmd)
        except KeyboardInterrupt:
            # ffmpeg already caught the same SIGINT and finalized the file.
            proc = None
        if proc is None or proc.returncode == 0:
            if out.is_file() and out.stat().st_size > 44:
                return out
            last_err = "пустая запись"
            continue
        last_err = f"ffmpeg ({source[1]}) rc={proc.returncode}"
        print(f"voice2dir: источник {source[1]} недоступен, пробую следующий...", file=sys.stderr)

    out.unlink(missing_ok=True)
    raise AsrError(f"не удалось записать звук с микрофона: {last_err}")
