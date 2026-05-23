"""Tests for audiobook_ish.synthesize."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audiobook_ish import AudiobookIshError, Sentence
from audiobook_ish.synthesize import (
    DEFAULT_SAMPLE_RATE,
    PipelineLike,
    sentence_wav_path,
    synthesize,
)


class FakePipeline:
    """A KPipeline-compatible callable for tests.

    Produces silent audio whose length is deterministically derived from the
    text length and the requested speed, so timing assertions are stable.
    Yields one segment for short text, two segments for longer text -- this
    mirrors Kokoro's behavior of splitting input internally.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, chars_per_sec: float = 20.0) -> None:
        self.sample_rate = sample_rate
        self.chars_per_sec = chars_per_sec
        self.calls: list[tuple[str, str, float]] = []

    def __call__(self, text: str, voice: str, speed: float):
        self.calls.append((text, voice, speed))
        duration_sec = max(0.1, len(text) / (self.chars_per_sec * speed))
        n_samples = int(duration_sec * self.sample_rate)
        audio = np.zeros(n_samples, dtype=np.float32)

        if len(text) > 50:
            mid = n_samples // 2
            yield ("g1", "p1", audio[:mid])
            yield ("g2", "p2", audio[mid:])
        else:
            yield ("g1", "p1", audio)


class EmptyPipeline:
    """Yields nothing -- simulates a degenerate Kokoro response."""

    def __call__(self, text: str, voice: str, speed: float):
        return iter(())


@pytest.fixture
def sample_sentences() -> list[Sentence]:
    return [
        Sentence(id=0, text="Hello world.", page=1, bbox=(0.0, 0.0, 100.0, 12.0)),
        Sentence(id=1, text="This is the second sentence.", page=1, bbox=(0.0, 14.0, 200.0, 26.0)),
        Sentence(
            id=2,
            text="And here is a much longer third sentence that should split.",
            page=2,
            bbox=(0.0, 28.0, 400.0, 40.0),
        ),
    ]


class TestSynthesize:
    def test_creates_wavs_for_each_sentence(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        pipeline = FakePipeline()
        out = synthesize(sample_sentences, tmp_path, pipeline=pipeline)

        for s in out:
            wav = sentence_wav_path(tmp_path, s.id)
            assert wav.is_file(), f"missing wav for sentence {s.id}"

    def test_timings_are_cumulative_and_monotonic(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        pipeline = FakePipeline()
        out = synthesize(sample_sentences, tmp_path, pipeline=pipeline)

        assert out[0].start_sec == 0.0
        for prev, curr in zip(out, out[1:]):
            assert prev.end_sec == pytest.approx(curr.start_sec)
            assert curr.end_sec > curr.start_sec

    def test_durations_match_wav_files(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        pipeline = FakePipeline()
        out = synthesize(sample_sentences, tmp_path, pipeline=pipeline)

        for s in out:
            wav = sentence_wav_path(tmp_path, s.id)
            info = sf.info(str(wav))
            on_disk = info.frames / info.samplerate
            assert s.end_sec - s.start_sec == pytest.approx(on_disk, abs=1e-4)

    def test_handles_multi_segment_output(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        """A long sentence triggers FakePipeline's 2-segment branch; output is concatenated."""
        pipeline = FakePipeline()
        synthesize(sample_sentences, tmp_path, pipeline=pipeline)

        long_wav = sentence_wav_path(tmp_path, 2)  # the long sentence
        audio, _ = sf.read(str(long_wav))
        expected_samples = int(
            (len(sample_sentences[2].text) / (pipeline.chars_per_sec * 1.2))
            * pipeline.sample_rate
        )
        assert abs(len(audio) - expected_samples) <= 1

    def test_progress_callback_fires_once_per_sentence(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        seen: list[tuple[int, int]] = []

        def cb(idx: int, sent: Sentence) -> None:
            seen.append((idx, sent.id))
            assert sent.start_sec is not None and sent.end_sec is not None

        synthesize(sample_sentences, tmp_path, pipeline=FakePipeline(), on_progress=cb)
        assert seen == [(0, 0), (1, 1), (2, 2)]

    def test_resumes_from_existing_wavs(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        """Pre-existing WAVs are not re-synthesized; their disk duration is used."""
        first = FakePipeline()
        synthesize(sample_sentences[:2], tmp_path, pipeline=first)
        assert len(first.calls) == 2

        # Reset start/end on the full list; second run should skip the first two
        # sentences and only synthesize the third.
        for s in sample_sentences:
            s.start_sec = None
            s.end_sec = None

        second = FakePipeline()
        out = synthesize(sample_sentences, tmp_path, pipeline=second)

        assert len(second.calls) == 1
        assert second.calls[0][0] == sample_sentences[2].text

        # Timings are still globally cumulative across resumed + new.
        assert out[0].start_sec == 0.0
        for prev, curr in zip(out, out[1:]):
            assert prev.end_sec == pytest.approx(curr.start_sec)

    def test_pipeline_not_loaded_when_all_wavs_exist(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        """If every WAV already exists, the synthesize() call should never touch
        the pipeline. We assert this by passing `pipeline=None` and an
        environment where the real Kokoro would fail to load (we don't even
        attempt it). The fake pre-fills the WAVs."""
        synthesize(sample_sentences, tmp_path, pipeline=FakePipeline())

        for s in sample_sentences:
            s.start_sec = None
            s.end_sec = None

        # With all WAVs present, passing pipeline=None must NOT trigger a load.
        # If it did, the import would (likely) succeed in dev env but we still
        # want to assert no synthesis call happened. We use a sentinel pipeline
        # that raises if invoked.
        class ExplodingPipeline:
            def __call__(self, *a, **kw):  # pragma: no cover
                raise AssertionError("pipeline should not have been called")

        out = synthesize(sample_sentences, tmp_path, pipeline=ExplodingPipeline())
        for s in out:
            assert s.start_sec is not None and s.end_sec is not None

    def test_raises_when_pipeline_returns_nothing(
        self, tmp_path: Path, sample_sentences: list[Sentence]
    ) -> None:
        with pytest.raises(AudiobookIshError, match="no audio"):
            synthesize(sample_sentences[:1], tmp_path, pipeline=EmptyPipeline())

    def test_raises_on_empty_sentence_text(self, tmp_path: Path) -> None:
        empty = [Sentence(id=0, text="   ", page=1, bbox=(0, 0, 10, 10))]
        with pytest.raises(AudiobookIshError, match="empty sentence"):
            synthesize(empty, tmp_path, pipeline=FakePipeline())


class TestSynthesizeIntegration:
    """Heavyweight: runs the real Kokoro model. Opt-in via env var."""

    def test_real_kokoro_first_three_sentences(self, tmp_path: Path, real_pdf: Path) -> None:
        if not os.environ.get("AUDIOBOOK_ISH_RUN_KOKORO"):
            pytest.skip("Set AUDIOBOOK_ISH_RUN_KOKORO=1 to run real Kokoro synthesis")

        from audiobook_ish.extract import extract_sentences

        sentences = extract_sentences(real_pdf)[1:4]  # skip the long title-page sentence
        out = synthesize(sentences, tmp_path)

        assert out[0].start_sec == 0.0
        for prev, curr in zip(out, out[1:]):
            assert prev.end_sec == pytest.approx(curr.start_sec)

        for s in out:
            wav = sentence_wav_path(tmp_path, s.id)
            assert wav.is_file()
            info = sf.info(str(wav))
            assert info.samplerate == DEFAULT_SAMPLE_RATE
            assert info.frames > 0
