"""Concatenate per-sentence WAVs into a single MP3 via ffmpeg.

Uses ffmpeg's concat demuxer:

    ffmpeg -y -f concat -safe 0 -i list.txt -c:a libmp3lame -b:a 128k out.mp3

The list file contains one `file '<absolute-path>'` line per WAV in order.
Paths are emitted with forward slashes so they parse cleanly inside the
single-quoted concat directive on Windows.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import AudiobookIshError

log = logging.getLogger(__name__)

DEFAULT_BITRATE = "128k"
_SENT_WAV_RE = re.compile(r"^sent_(\d+)\.wav$")


def find_ffmpeg() -> str:
    """Locate ffmpeg via env var or PATH; raise AudiobookIshError if absent."""
    explicit = os.environ.get("AUDIOBOOK_ISH_FFMPEG")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise AudiobookIshError(
        "ffmpeg not found. Install it and put it on PATH, or set "
        "AUDIOBOOK_ISH_FFMPEG to its full path."
    )


def _collect_sentence_wavs(sentences_dir: Path) -> list[Path]:
    """Return sent_*.wav files sorted by their numeric id; verify no gaps."""
    wavs: list[tuple[int, Path]] = []
    for entry in sentences_dir.iterdir():
        if not entry.is_file():
            continue
        match = _SENT_WAV_RE.match(entry.name)
        if not match:
            continue
        wavs.append((int(match.group(1)), entry))

    if not wavs:
        raise AudiobookIshError(f"No sent_NNNNN.wav files found in {sentences_dir}")

    wavs.sort(key=lambda pair: pair[0])
    ids = [pair[0] for pair in wavs]
    expected = list(range(ids[0], ids[-1] + 1))
    missing = sorted(set(expected) - set(ids))
    if missing:
        sample = ", ".join(str(m) for m in missing[:10])
        more = f" (and {len(missing) - 10} more)" if len(missing) > 10 else ""
        raise AudiobookIshError(
            f"Missing sentence WAVs in {sentences_dir}: {sample}{more}"
        )

    return [pair[1] for pair in wavs]


def _write_concat_list(wavs: list[Path], list_path: Path) -> None:
    """Write an ffmpeg concat-demuxer manifest with forward-slash paths."""
    lines = [f"file '{wav.resolve().as_posix()}'\n" for wav in wavs]
    list_path.write_text("".join(lines), encoding="utf-8")


def combine(
    sentences_dir: Path,
    output_mp3: Path,
    bitrate: str = DEFAULT_BITRATE,
    ffmpeg_path: str | None = None,
) -> None:
    """Concatenate every sent_NNNNN.wav in `sentences_dir` into one MP3.

    Args:
        sentences_dir: directory containing `sent_00000.wav`, `sent_00001.wav`, ...
            Files must form a contiguous run of ids (no gaps).
        output_mp3: destination path. Parent dirs are created if missing.
        bitrate: libmp3lame `-b:a` value, e.g. `"128k"`, `"192k"`, `"96k"`.
        ffmpeg_path: explicit ffmpeg binary; if omitted, uses
            `AUDIOBOOK_ISH_FFMPEG` env var or `shutil.which("ffmpeg")`.

    Raises:
        AudiobookIshError on missing ffmpeg, missing inputs, gaps in ids,
        or non-zero ffmpeg exit.
    """
    sentences_dir = Path(sentences_dir)
    output_mp3 = Path(output_mp3)
    if not sentences_dir.is_dir():
        raise AudiobookIshError(f"Sentences directory not found: {sentences_dir}")

    wavs = _collect_sentence_wavs(sentences_dir)
    ffmpeg = ffmpeg_path or find_ffmpeg()

    output_mp3.parent.mkdir(parents=True, exist_ok=True)

    # NamedTemporaryFile on Windows cannot be reopened while still held by the
    # current process, so close+pass-by-path is more portable than delete=False.
    list_fd, list_name = tempfile.mkstemp(suffix=".txt", prefix="audiobook_ish_concat_")
    os.close(list_fd)
    list_path = Path(list_name)

    try:
        _write_concat_list(wavs, list_path)

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path.as_posix(),
            "-c:a", "libmp3lame",
            "-b:a", bitrate,
            output_mp3.as_posix(),
        ]
        log.info(
            "Combining %d WAVs from %s -> %s @ %s",
            len(wavs), sentences_dir, output_mp3, bitrate,
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip()[-500:]
            raise AudiobookIshError(
                f"ffmpeg failed (exit {result.returncode}): {tail}"
            )
    finally:
        try:
            list_path.unlink()
        except OSError:
            pass
