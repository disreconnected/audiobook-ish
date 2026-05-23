"""Concatenate per-sentence WAVs into one MP3 via ffmpeg.

See PLAN.md M3.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import AudiobookIshError


def find_ffmpeg() -> str:
    """Locate ffmpeg via env var or PATH."""
    explicit = os.environ.get("AUDIOBOOK_ISH_FFMPEG")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise AudiobookIshError(
        "ffmpeg not found. Install it or set AUDIOBOOK_ISH_FFMPEG to its full path."
    )


def combine(sentences_dir: Path, output_mp3: Path, bitrate: str = "128k") -> None:
    """Concatenate every sent_NNNNN.wav in `sentences_dir` into a single MP3.

    TODO(M3): implement using `ffmpeg -f concat -safe 0 -i list.txt -c:a libmp3lame -b:a <bitrate>`.
    """
    raise NotImplementedError("M3 not yet implemented — see PLAN.md")
