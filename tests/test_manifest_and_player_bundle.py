"""Tests for manifest serialization + player bundling helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiobook_ish import AudiobookIshError, PageInfo, Sentence
from audiobook_ish.chapters import detect_chapters
from audiobook_ish.manifest import (
    build_manifest,
    manifest_to_dict,
    write_manifest,
    write_manifest_js,
)
from audiobook_ish.player_bundle import bundle_player


def _sample_sentences() -> list[Sentence]:
    return [
        Sentence(id=0, text="One.", page=2, bbox=(0.0, 0.0, 10.0, 10.0), start_sec=0.0, end_sec=1.2),
        Sentence(id=1, text="Two.", page=3, bbox=(0.0, 12.0, 10.0, 22.0), start_sec=1.2, end_sec=2.8),
    ]


class TestManifest:
    def test_build_manifest_infers_page_count_from_pages(self) -> None:
        pages = [
            PageInfo(1, "pages/page_001.png", 600, 900, 300.0, 450.0),
            PageInfo(2, "pages/page_002.png", 600, 900, 300.0, 450.0),
        ]
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=pages,
            sentences=_sample_sentences(),
        )
        assert m.page_count == 2
        assert m.duration_sec == pytest.approx(2.8)

    def test_build_manifest_infers_page_count_from_sentences_when_no_pages(self) -> None:
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=[],
            sentences=_sample_sentences(),
        )
        assert m.page_count == 3

    def test_build_manifest_respects_explicit_page_count(self) -> None:
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=[],
            sentences=_sample_sentences(),
            page_count=767,
        )
        assert m.page_count == 767

    def test_write_manifest_json(self, tmp_path: Path) -> None:
        chapters = detect_chapters(
            [
                Sentence(id=0, text="CHAPTER I", page=1, bbox=(0, 0, 10, 10), start_sec=0.0, end_sec=0.5),
                Sentence(id=1, text="One.", page=1, bbox=(0, 0, 10, 10), start_sec=0.5, end_sec=1.2),
            ]
        )
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=[],
            sentences=_sample_sentences(),
            chapters=chapters,
        )
        out = tmp_path / "manifest.json"
        write_manifest(m, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["source_pdf"] == "book.pdf"
        assert payload["sentences"][0]["bbox"] == [0.0, 0.0, 10.0, 10.0]
        assert payload["duration_sec"] == pytest.approx(2.8)
        assert payload["chapters"] == [
            {"title": "Chapter I", "sentence_id": 0, "page": 1, "start_sec": 0.0}
        ]

    def test_write_manifest_js_sets_window_global(self, tmp_path: Path) -> None:
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=[],
            sentences=_sample_sentences(),
        )
        out = tmp_path / "manifest.js"
        write_manifest_js(m, out)
        text = out.read_text(encoding="utf-8")
        assert text.startswith("window.AUDIOBOOK_ISH_MANIFEST=")
        assert text.rstrip().endswith(";")

    def test_manifest_to_dict_is_json_serializable(self) -> None:
        m = build_manifest(
            source_pdf="book.pdf",
            voice="af_nicole",
            speed=1.2,
            sample_rate=24000,
            pages=[],
            sentences=_sample_sentences(),
        )
        payload = manifest_to_dict(m)
        encoded = json.dumps(payload)
        assert isinstance(encoded, str)


class TestPlayerBundle:
    def test_bundle_player_copies_html_css_js(self, tmp_path: Path) -> None:
        source = tmp_path / "player-src"
        source.mkdir()
        (source / "index.html").write_text("<html></html>", encoding="utf-8")
        (source / "player.css").write_text("body{}", encoding="utf-8")
        (source / "player.js").write_text("console.log(1)", encoding="utf-8")
        (source / "assets").mkdir()
        (source / "assets" / "icon.txt").write_text("x", encoding="utf-8")

        out = tmp_path / "bundle"
        bundle_player(out, source)

        assert (out / "player.html").is_file()
        assert (out / "player.css").is_file()
        assert (out / "player.js").is_file()
        assert (out / "assets" / "icon.txt").is_file()

    def test_bundle_player_errors_on_missing_source(self, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="Player source directory not found"):
            bundle_player(tmp_path / "bundle", tmp_path / "missing")

    def test_bundle_player_errors_on_missing_asset(self, tmp_path: Path) -> None:
        source = tmp_path / "player-src"
        source.mkdir()
        (source / "index.html").write_text("<html></html>", encoding="utf-8")
        (source / "player.css").write_text("body{}", encoding="utf-8")
        # missing player.js
        with pytest.raises(AudiobookIshError, match="Missing player asset"):
            bundle_player(tmp_path / "bundle", source)
