"""Tests for audiobook_ish.combine."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audiobook_ish import AudiobookIshError
from audiobook_ish.combine import combine, find_ffmpeg


SAMPLE_RATE = 24000


def _has_ffmpeg() -> bool:
    if os.environ.get("AUDIOBOOK_ISH_FFMPEG"):
        return Path(os.environ["AUDIOBOOK_ISH_FFMPEG"]).is_file()
    return shutil.which("ffmpeg") is not None


requires_ffmpeg = pytest.mark.skipif(
    not _has_ffmpeg(), reason="ffmpeg not on PATH and AUDIOBOOK_ISH_FFMPEG unset"
)


def _write_silent_wav(path: Path, duration_sec: float = 0.5) -> None:
    n_samples = int(duration_sec * SAMPLE_RATE)
    audio = np.zeros(n_samples, dtype=np.float32)
    sf.write(str(path), audio, SAMPLE_RATE)


@pytest.fixture
def sentences_dir(tmp_path: Path) -> Path:
    """Three contiguous silent sentence WAVs."""
    d = tmp_path / "sentences"
    d.mkdir()
    for i in range(3):
        _write_silent_wav(d / f"sent_{i:05d}.wav", duration_sec=0.5)
    return d


class TestFindFfmpeg:
    def test_respects_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "ffmpeg.exe"
        fake.write_text("not a real binary, just exists for the file check")
        monkeypatch.setenv("AUDIOBOOK_ISH_FFMPEG", str(fake))
        assert find_ffmpeg() == str(fake)

    def test_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUDIOBOOK_ISH_FFMPEG", raising=False)
        monkeypatch.setattr("audiobook_ish.combine.shutil.which", lambda _: None)
        with pytest.raises(AudiobookIshError, match="ffmpeg not found"):
            find_ffmpeg()


class TestCombineValidation:
    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="Sentences directory not found"):
            combine(tmp_path / "nope", tmp_path / "out.mp3")

    def test_empty_dir_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "sentences"
        empty.mkdir()
        with pytest.raises(AudiobookIshError, match="No sent_NNNNN.wav"):
            combine(empty, tmp_path / "out.mp3")

    def test_gap_in_ids_raises(self, tmp_path: Path) -> None:
        d = tmp_path / "sentences"
        d.mkdir()
        _write_silent_wav(d / "sent_00000.wav")
        _write_silent_wav(d / "sent_00002.wav")  # skip 1
        with pytest.raises(AudiobookIshError, match="Missing sentence WAVs"):
            combine(d, tmp_path / "out.mp3")

    def test_ignores_non_sentence_files(self, sentences_dir: Path, tmp_path: Path) -> None:
        """Files like progress.json next to the WAVs must not break collection."""
        (sentences_dir / "progress.json").write_text("{}", encoding="utf-8")
        (sentences_dir / "stray.wav").touch()  # different prefix
        # Should NOT raise -- only sent_NNNNN.wav files are collected.
        # We just need to confirm collection succeeds (skip the actual ffmpeg run).
        from audiobook_ish.combine import _collect_sentence_wavs

        wavs = _collect_sentence_wavs(sentences_dir)
        assert len(wavs) == 3
        assert all(w.name.startswith("sent_") for w in wavs)


@requires_ffmpeg
class TestCombineEndToEnd:
    def test_produces_playable_mp3(self, sentences_dir: Path, tmp_path: Path) -> None:
        out = tmp_path / "audiobook.mp3"
        combine(sentences_dir, out)

        assert out.is_file(), "output MP3 was not written"
        assert out.stat().st_size > 0

        # Probe back via soundfile (libsndfile can read MP3 in recent versions).
        # If that fails on this build, at least assert ffprobe-compatible size.
        try:
            info = sf.info(str(out))
            # 3 silent WAVs of 0.5s each -> 1.5s total (some encoder padding ok).
            assert info.duration == pytest.approx(1.5, abs=0.2)
        except Exception:
            # libsndfile MP3 support may be unavailable; size check is enough.
            assert out.stat().st_size > 1000  # at least 1 KB of MP3 data

    def test_respects_custom_output_directory(
        self, sentences_dir: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "nested" / "deeper" / "book.mp3"
        combine(sentences_dir, out)
        assert out.is_file()
