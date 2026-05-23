"""Kokoro TTS per sentence, resumable.

`synthesize()` walks a list of Sentence objects, producing
`<output_dir>/sentences/sent_NNNNN.wav` for each one and filling in
`start_sec` / `end_sec` (cumulative, with the first sentence starting at 0).

Resumability is the design centerpiece: every sentence whose WAV already
exists on disk is skipped and its duration is recovered from the file.
That means a crashed or killed run can be restarted with the same call
and it picks up at the first missing WAV.

The Kokoro pipeline is lazily constructed (heavy import + ~20s of model
loading) only if there's at least one missing WAV. Tests inject a
FakePipeline to avoid loading the real model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import soundfile as sf

from . import AudiobookIshError, Sentence

log = logging.getLogger(__name__)

DEFAULT_VOICE = "af_nicole"
DEFAULT_SPEED = 1.2
DEFAULT_SAMPLE_RATE = 24000


class PipelineLike(Protocol):
    """The subset of `kokoro.KPipeline` we need.

    Calling it with `(text, voice=..., speed=...)` yields one or more
    `(graphemes, phonemes, audio_ndarray)` tuples; we only consume the third.
    """

    def __call__(
        self, text: str, voice: str, speed: float
    ) -> Iterable[tuple[Any, Any, np.ndarray]]: ...


ProgressCallback = Callable[[int, Sentence], None]


def sentence_wav_path(output_dir: Path, sentence_id: int) -> Path:
    """Canonical on-disk location for a sentence's WAV."""
    return Path(output_dir) / "sentences" / f"sent_{sentence_id:05d}.wav"


def _load_default_pipeline(lang_code: str = "a") -> PipelineLike:
    """Lazily import + construct the real Kokoro pipeline."""
    try:
        from kokoro import KPipeline  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise AudiobookIshError(
            "The `kokoro` package is not installed. `pip install kokoro` first."
        ) from exc
    return KPipeline(lang_code=lang_code)


def _duration_seconds(wav_path: Path) -> float:
    """Read a WAV's duration without loading its samples into memory."""
    info = sf.info(str(wav_path))
    return info.frames / float(info.samplerate)


def _synthesize_one(
    pipeline: PipelineLike,
    sentence: Sentence,
    voice: str,
    speed: float,
    sample_rate: int,
    wav_path: Path,
) -> float:
    """Synthesize one sentence to disk; return its duration in seconds."""
    if not sentence.text.strip():
        raise AudiobookIshError(
            f"Refusing to synthesize empty sentence #{sentence.id}"
        )

    segments = [audio for _, _, audio in pipeline(sentence.text, voice=voice, speed=speed)]
    if not segments:
        raise AudiobookIshError(
            f"Kokoro returned no audio for sentence #{sentence.id}: {sentence.text[:80]!r}"
        )

    audio = segments[0] if len(segments) == 1 else np.concatenate(segments)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav_path), audio, sample_rate)
    return len(audio) / float(sample_rate)


def synthesize(
    sentences: list[Sentence],
    output_dir: Path,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    pipeline: PipelineLike | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[Sentence]:
    """Synthesize every sentence to a WAV; fill in cumulative start/end times.

    Args:
        sentences: extracted sentences (from `extract.extract_sentences`).
        output_dir: root directory; WAVs go in `<output_dir>/sentences/`.
        voice: Kokoro voice name.
        speed: playback speed (Kokoro is shape-preserving; faster speed
            produces shorter audio).
        sample_rate: target sample rate for new WAVs (Kokoro defaults to 24kHz).
        pipeline: pre-constructed Kokoro pipeline (or compatible callable).
            If `None`, the real `kokoro.KPipeline(lang_code='a')` is loaded
            lazily on first miss.
        on_progress: optional callback `(idx_in_list, sentence)` invoked after
            each sentence completes (whether it was synthesized or recovered
            from an existing WAV). Used by the CLI to write partial manifest
            checkpoints.

    Returns:
        The same `sentences` list, with `start_sec` and `end_sec` mutated
        in place. Total duration is `sentences[-1].end_sec`.

    Notes:
        - Resumable: if `<output_dir>/sentences/sent_NNNNN.wav` already
          exists, its on-disk duration is used and Kokoro is not invoked.
        - The pipeline is only loaded if at least one WAV is missing.
        - Voice / speed changes are NOT detected; if you want to regenerate
          a sentence with different settings, delete its WAV first.
    """
    output_dir = Path(output_dir)
    (output_dir / "sentences").mkdir(parents=True, exist_ok=True)

    cursor = 0.0
    n_synthesized = 0
    n_resumed = 0

    for idx, sentence in enumerate(sentences):
        wav_path = sentence_wav_path(output_dir, sentence.id)

        if wav_path.exists():
            duration = _duration_seconds(wav_path)
            n_resumed += 1
        else:
            if pipeline is None:
                log.info("Loading Kokoro pipeline (first missing WAV)...")
                pipeline = _load_default_pipeline()
            duration = _synthesize_one(
                pipeline, sentence, voice, speed, sample_rate, wav_path
            )
            n_synthesized += 1
            log.info(
                "Synthesized #%d (p%d, %d chars) -> %.1fs",
                sentence.id, sentence.page, len(sentence.text), duration,
            )

        sentence.start_sec = cursor
        sentence.end_sec = cursor + duration
        cursor += duration

        if on_progress is not None:
            on_progress(idx, sentence)

    log.info(
        "Done. %d new, %d resumed; total %.1f sec (%.2f hr).",
        n_synthesized, n_resumed, cursor, cursor / 3600,
    )
    return sentences
