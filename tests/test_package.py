"""Tests for package.py: m4b ffmetadata + zip bundling."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from audiobook_ish import AudiobookIshError
from audiobook_ish.package import build_ffmeta, package_m4b, package_zip


class TestBuildFFMeta:
    def test_includes_global_header(self) -> None:
        text = build_ffmeta({"source_pdf": "book.pdf", "voice": "af_nicole", "speed": 1.2})
        assert text.startswith(";FFMETADATA1\n")
        assert "title=book.pdf" in text
        assert "genre=Audiobook" in text

    def test_renders_chapters_with_timebase_in_ms(self) -> None:
        manifest = {
            "source_pdf": "book.pdf",
            "duration_sec": 30.0,
            "chapters": [
                {"title": "Chapter I", "start_sec": 0.0},
                {"title": "Chapter II", "start_sec": 12.5},
            ],
        }
        text = build_ffmeta(manifest)
        assert "[CHAPTER]" in text
        assert "TIMEBASE=1/1000" in text
        assert "START=0\nEND=12499\ntitle=Chapter I" in text
        assert "START=12500\nEND=30000\ntitle=Chapter II" in text

    def test_prepends_intro_if_first_chapter_not_at_zero(self) -> None:
        manifest = {
            "source_pdf": "book.pdf",
            "duration_sec": 200.0,
            "chapters": [{"title": "Chapter I", "start_sec": 30.0}],
        }
        text = build_ffmeta(manifest)
        # Intro chapter from 0 -> just before Chapter I, then Chapter I -> end
        assert "title=Intro" in text
        assert "START=0\nEND=29999\ntitle=Intro" in text
        assert "START=30000\nEND=200000\ntitle=Chapter I" in text

    def test_no_chapter_block_when_chapters_empty(self) -> None:
        text = build_ffmeta({"source_pdf": "book.pdf", "duration_sec": 10.0, "chapters": []})
        assert "[CHAPTER]" not in text

    def test_chapters_sorted_by_start(self) -> None:
        manifest = {
            "source_pdf": "book.pdf",
            "duration_sec": 50.0,
            "chapters": [
                {"title": "Z", "start_sec": 20.0},
                {"title": "A", "start_sec": 0.0},
            ],
        }
        text = build_ffmeta(manifest)
        a_idx = text.index("title=A")
        z_idx = text.index("title=Z")
        assert a_idx < z_idx

    def test_empty_chapter_title_falls_back_to_default(self) -> None:
        manifest = {
            "source_pdf": "book.pdf",
            "duration_sec": 10.0,
            "chapters": [{"title": "", "start_sec": 0.0}],
        }
        text = build_ffmeta(manifest)
        assert "title=Chapter 1" in text


class TestPackageM4b:
    def test_invokes_ffmpeg_with_expected_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Stage a fake output dir
        out = tmp_path / "build"
        out.mkdir()
        (out / "audiobook.mp3").write_bytes(b"FAKEMP3")
        manifest = {
            "source_pdf": "book.pdf",
            "voice": "af_nicole",
            "speed": 1.2,
            "sample_rate": 24000,
            "duration_sec": 12.0,
            "chapters": [{"title": "Chapter I", "start_sec": 0.0}],
        }
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        captured: dict = {}

        def fake_run(cmd, capture_output, text):  # type: ignore[no-untyped-def]
            captured["cmd"] = list(cmd)
            # Two -i flags: input MP3, then ffmeta. Grab the second.
            i_positions = [i for i, x in enumerate(cmd) if x == "-i"]
            ffmeta_path = Path(cmd[i_positions[1] + 1])
            captured["ffmeta_text"] = ffmeta_path.read_text(encoding="utf-8")

            class R:
                returncode = 0
                stderr = ""
                stdout = ""

            return R()

        monkeypatch.setattr("audiobook_ish.package.subprocess.run", fake_run)
        monkeypatch.setattr("audiobook_ish.package.find_ffmpeg", lambda: "ffmpeg-stub")

        dest = tmp_path / "book.m4b"
        package_m4b(out, dest, bitrate="48k")

        cmd = captured["cmd"]
        assert cmd[0] == "ffmpeg-stub"
        assert "-c:a" in cmd and "aac" in cmd
        assert "-b:a" in cmd and "48k" in cmd
        assert "-map_chapters" in cmd
        assert cmd[-1].endswith("book.m4b")
        assert "title=Chapter I" in captured["ffmeta_text"]

    def test_errors_on_missing_mp3(self, tmp_path: Path) -> None:
        out = tmp_path / "build"
        out.mkdir()
        with pytest.raises(AudiobookIshError, match="audiobook.mp3"):
            package_m4b(out, tmp_path / "book.m4b")

    def test_errors_on_missing_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "build"
        out.mkdir()
        (out / "audiobook.mp3").write_bytes(b"FAKE")
        monkeypatch.setattr("audiobook_ish.package.find_ffmpeg", lambda: "ffmpeg-stub")
        with pytest.raises(AudiobookIshError, match="manifest.json"):
            package_m4b(out, tmp_path / "book.m4b")


class TestPackageZip:
    def _stage_build(self, root: Path) -> Path:
        out = root / "build"
        out.mkdir()
        (out / "audiobook.mp3").write_bytes(b"\x00" * 32)
        (out / "manifest.json").write_text("{}", encoding="utf-8")
        (out / "manifest.js").write_text("window.AUDIOBOOK_ISH_MANIFEST={};\n", encoding="utf-8")
        (out / "player.html").write_text("<html></html>", encoding="utf-8")
        (out / "player.css").write_text("body{}", encoding="utf-8")
        (out / "player.js").write_text("// js", encoding="utf-8")
        (out / "pages").mkdir()
        (out / "pages" / "page_001.png").write_bytes(b"\x89PNG\r\n")
        (out / "pages" / "page_002.png").write_bytes(b"\x89PNG\r\n")
        (out / "assets").mkdir()
        (out / "assets" / "icon.txt").write_text("x", encoding="utf-8")
        (out / "sentences").mkdir()
        (out / "sentences" / "sent_00000.wav").write_bytes(b"\x00")
        (out / "sentences.json").write_text("{}", encoding="utf-8")
        return out

    def test_zip_contains_player_audio_pages_assets(self, tmp_path: Path) -> None:
        out = self._stage_build(tmp_path)
        dest = tmp_path / "book.zip"
        package_zip(out, dest)

        with zipfile.ZipFile(dest) as zf:
            names = set(zf.namelist())

        assert "book/player.html" in names
        assert "book/player.css" in names
        assert "book/player.js" in names
        assert "book/manifest.json" in names
        assert "book/manifest.js" in names
        assert "book/audiobook.mp3" in names
        assert "book/pages/page_001.png" in names
        assert "book/pages/page_002.png" in names
        assert "book/assets/icon.txt" in names

    def test_zip_excludes_sentences_and_sentences_json(self, tmp_path: Path) -> None:
        out = self._stage_build(tmp_path)
        dest = tmp_path / "book.zip"
        package_zip(out, dest)

        with zipfile.ZipFile(dest) as zf:
            names = set(zf.namelist())

        assert not any(n.endswith(".wav") for n in names)
        assert "book/sentences.json" not in names
        assert not any("sentences/" in n for n in names)

    def test_zip_no_pages_flag_skips_pages(self, tmp_path: Path) -> None:
        out = self._stage_build(tmp_path)
        dest = tmp_path / "book.zip"
        package_zip(out, dest, include_pages=False)

        with zipfile.ZipFile(dest) as zf:
            names = set(zf.namelist())

        assert not any("pages/" in n for n in names)
        assert "book/audiobook.mp3" in names

    def test_zip_uses_dest_stem_as_root_folder(self, tmp_path: Path) -> None:
        out = self._stage_build(tmp_path)
        dest = tmp_path / "crime-and-punishment.zip"
        package_zip(out, dest)

        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()

        assert all(n.startswith("crime-and-punishment/") for n in names)

    def test_zip_errors_on_missing_output_dir(self, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="Output directory not found"):
            package_zip(tmp_path / "missing", tmp_path / "book.zip")

    def test_zip_errors_on_empty_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "build"
        out.mkdir()
        with pytest.raises(AudiobookIshError, match="empty zip"):
            package_zip(out, tmp_path / "book.zip")
