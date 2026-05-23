"""Tests for audiobook_ish.render."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from audiobook_ish import AudiobookIshError, PageInfo
from audiobook_ish.render import render_pages


class TestRenderPages:
    def test_missing_pdf_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="not found"):
            render_pages(tmp_path / "nope.pdf", tmp_path)

    def test_invalid_dpi_raises(self, tiny_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="DPI must be positive"):
            render_pages(tiny_pdf, tmp_path, dpi=0)

    def test_renders_every_page(self, tiny_pdf: Path, tmp_path: Path) -> None:
        infos = render_pages(tiny_pdf, tmp_path, dpi=100)

        assert len(infos) == 2
        for page_num in (1, 2):
            png = tmp_path / "pages" / f"page_{page_num:03d}.png"
            assert png.is_file(), f"missing PNG for page {page_num}"

    def test_pageinfo_fields_are_populated(self, tiny_pdf: Path, tmp_path: Path) -> None:
        infos = render_pages(tiny_pdf, tmp_path, dpi=100)

        for i, info in enumerate(infos, start=1):
            assert isinstance(info, PageInfo)
            assert info.number == i
            assert info.image == f"pages/page_{i:03d}.png"
            assert info.width_px > 0 and info.height_px > 0
            assert info.pdf_width_pt > 0 and info.pdf_height_pt > 0

    def test_pixel_dims_scale_with_dpi(self, tiny_pdf: Path, tmp_path: Path) -> None:
        small = render_pages(tiny_pdf, tmp_path / "small", dpi=72)
        large = render_pages(tiny_pdf, tmp_path / "large", dpi=144)

        # At exactly 2x the DPI, pixel dims should roughly double.
        for s, l in zip(small, large):
            assert l.width_px == pytest.approx(s.width_px * 2, rel=0.05)
            assert l.height_px == pytest.approx(s.height_px * 2, rel=0.05)

    def test_progress_callback_fires_once_per_page(
        self, tiny_pdf: Path, tmp_path: Path
    ) -> None:
        seen: list[int] = []

        def cb(page_num: int, info: PageInfo) -> None:
            seen.append(page_num)
            assert info.number == page_num

        render_pages(tiny_pdf, tmp_path, dpi=100, on_progress=cb)
        assert seen == [1, 2]

    def test_resumes_existing_pngs_without_rerendering(
        self, tiny_pdf: Path, tmp_path: Path
    ) -> None:
        """Existing PNGs should be kept; pixel dims read from disk."""
        first = render_pages(tiny_pdf, tmp_path, dpi=100)
        first_mtimes = {p.number: (tmp_path / p.image).stat().st_mtime_ns for p in first}

        # Re-run; PNG file mtimes should not change because we don't rewrite.
        second = render_pages(tiny_pdf, tmp_path, dpi=100)
        for info in second:
            current_mtime = (tmp_path / info.image).stat().st_mtime_ns
            assert current_mtime == first_mtimes[info.number]

        # Dims still come back correctly.
        for a, b in zip(first, second):
            assert a.width_px == b.width_px
            assert a.height_px == b.height_px

    def test_pad_width_grows_for_large_books(self, tmp_path: Path) -> None:
        """A 1500-page book should use 4-digit page filenames."""
        doc = pymupdf.open()
        for _ in range(1500):
            doc.new_page()
        big_pdf = tmp_path / "big.pdf"
        doc.save(big_pdf)
        doc.close()

        infos = render_pages(big_pdf, tmp_path, dpi=36)  # low DPI to keep test fast

        assert infos[0].image == "pages/page_0001.png"
        assert infos[-1].image == "pages/page_1500.png"
        assert (tmp_path / "pages" / "page_0001.png").is_file()
        assert (tmp_path / "pages" / "page_1500.png").is_file()
