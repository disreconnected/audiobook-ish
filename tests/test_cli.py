"""Tests for audiobook_ish.cli.__main__."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiobook_ish import AudiobookIshError, PageInfo, Sentence
from audiobook_ish.cli import __main__ as cli


def _sample_sentences() -> list[Sentence]:
    return [
        Sentence(id=10, text="One.", page=2, bbox=(0.0, 0.0, 10.0, 10.0)),
        Sentence(id=11, text="Two.", page=3, bbox=(0.0, 12.0, 10.0, 22.0)),
        Sentence(id=12, text="Three.", page=4, bbox=(0.0, 24.0, 10.0, 34.0)),
    ]


class TestCliSubcommands:
    def test_bundle_player_subcommand(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {}

        def fake_bundle(out: Path) -> None:
            called["out"] = out

        monkeypatch.setattr(cli, "bundle_player", fake_bundle)
        code = cli.main(["bundle-player", str(tmp_path)])
        assert code == 0
        assert called["out"] == tmp_path

    def test_extract_writes_json_and_reindexes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        out = tmp_path / "sentences.json"

        monkeypatch.setattr(cli, "extract_sentences", lambda _pdf: _sample_sentences())
        code = cli.main(["extract", str(pdf), "--out", str(out), "--max-sentences", "2"])
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        ids = [s["id"] for s in payload["sentences"]]
        assert ids == [0, 1]
        assert payload["count"] == 2

    def test_synthesize_writes_checkpoint_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentences_json = tmp_path / "sentences.json"
        payload = {
            "source_pdf": str(tmp_path / "book.pdf"),
            "count": 3,
            "sentences": [
                {
                    "id": 0,
                    "text": "One.",
                    "page": 1,
                    "bbox": [0, 0, 10, 10],
                    "start_sec": None,
                    "end_sec": None,
                },
                {
                    "id": 1,
                    "text": "Two.",
                    "page": 1,
                    "bbox": [0, 12, 10, 22],
                    "start_sec": None,
                    "end_sec": None,
                },
                {
                    "id": 2,
                    "text": "Three.",
                    "page": 1,
                    "bbox": [0, 24, 10, 34],
                    "start_sec": None,
                    "end_sec": None,
                },
            ],
        }
        sentences_json.write_text(json.dumps(payload), encoding="utf-8")
        out = tmp_path / "out"

        def fake_synthesize(**kwargs):
            sentences = kwargs["sentences"]
            on_progress = kwargs["on_progress"]
            t = 0.0
            for i, s in enumerate(sentences):
                s.start_sec = t
                s.end_sec = t + 1.0
                t += 1.0
                on_progress(i, s)
            return sentences

        monkeypatch.setattr(cli, "synthesize", fake_synthesize)
        code = cli.main(
            [
                "synthesize",
                str(sentences_json),
                "--out",
                str(out),
                "--checkpoint-every",
                "1",
            ]
        )
        assert code == 0
        assert (out / "manifest.json").is_file()
        assert (out / "manifest.js").is_file()
        assert (out / "sentences.json").is_file()

    def test_build_wires_pipeline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        out = tmp_path / "build"

        calls: list[str] = []

        monkeypatch.setattr(cli, "extract_sentences", lambda _pdf: _sample_sentences())

        def fake_synthesize(**kwargs):
            calls.append("synthesize")
            sentences = kwargs["sentences"]
            on_progress = kwargs["on_progress"]
            t = 0.0
            for i, s in enumerate(sentences):
                s.start_sec = t
                s.end_sec = t + 0.5
                t += 0.5
                on_progress(i, s)
            return sentences

        monkeypatch.setattr(cli, "synthesize", fake_synthesize)

        monkeypatch.setattr(
            cli,
            "render_pages",
            lambda _pdf, _out, dpi: [
                PageInfo(
                    number=1,
                    image="pages/page_001.png",
                    width_px=600,
                    height_px=900,
                    pdf_width_pt=300.0,
                    pdf_height_pt=450.0,
                )
            ],
        )

        def fake_combine(sentences_dir: Path, output_mp3: Path, bitrate: str, ffmpeg_path):
            calls.append("combine")
            output_mp3.parent.mkdir(parents=True, exist_ok=True)
            output_mp3.write_bytes(b"mp3")

        monkeypatch.setattr(cli, "combine", fake_combine)
        monkeypatch.setattr(cli, "bundle_player", lambda _out: calls.append("bundle"))

        code = cli.main(["build", str(pdf), "--out", str(out), "--checkpoint-every", "1"])
        assert code == 0
        assert calls == ["synthesize", "combine", "bundle"]
        assert (out / "manifest.json").is_file()
        assert (out / "manifest.js").is_file()
        assert (out / "sentences.json").is_file()
        assert (out / "audiobook.mp3").is_file()

    def test_errors_return_exit_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pdf = tmp_path / "missing.pdf"
        out = tmp_path / "x.json"

        def boom(_pdf):
            raise AudiobookIshError("boom")

        monkeypatch.setattr(cli, "extract_sentences", boom)
        code = cli.main(["extract", str(pdf), "--out", str(out)])
        assert code == 1
