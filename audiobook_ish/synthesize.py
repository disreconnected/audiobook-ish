"""Kokoro TTS per sentence, resumable.

Responsible for:
- holding a single KPipeline,
- synthesizing one sentence at a time,
- writing sentences/sent_NNNNN.wav,
- recording cumulative start_sec/end_sec on each Sentence,
- skipping sentences whose WAV already exists on disk.

See PLAN.md M2.
"""

from __future__ import annotations

from pathlib import Path

from . import Sentence


def synthesize(
    sentences: list[Sentence],
    output_dir: Path,
    voice: str = "af_nicole",
    speed: float = 1.2,
    sample_rate: int = 24000,
) -> list[Sentence]:
    """Synthesize each sentence, return the same list with timings filled in.

    Writes WAVs to `output_dir / "sentences" / sent_NNNNN.wav`.
    Resumable: existing WAVs are kept and their duration is read from disk.

    TODO(M2): implement.
    """
    raise NotImplementedError("M2 not yet implemented — see PLAN.md")
