"""Render each PDF page to a PNG at a fixed DPI; record pixel + PDF-point dims.

The pixel/point dims are stored in the manifest so the web player can map a
sentence's PDF-point bbox to pixel coordinates on the rendered page image.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pymupdf

from . import AudiobookIshError, PageInfo

log = logging.getLogger(__name__)

DEFAULT_DPI = 150

ProgressCallback = Callable[[int, PageInfo], None]


def _page_filename(page_number: int, n_digits: int) -> str:
    return f"page_{page_number:0{n_digits}d}.png"


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = DEFAULT_DPI,
    on_progress: ProgressCallback | None = None,
) -> list[PageInfo]:
    """Render every PDF page to `<output_dir>/pages/page_NNN.png`.

    Args:
        pdf_path: source PDF.
        output_dir: root output directory; PNGs are written under `pages/`.
        dpi: render resolution. 150 is the sweet spot for laptop reading
            (~500 KB/page for a typical 6x9 book). 100 if you want smaller.
        on_progress: optional `(page_number, page_info)` callback invoked
            after each page is rendered or recovered from cache.

    Returns:
        List of `PageInfo`, one per PDF page, ordered by page number.

    Resumable: if a PNG already exists at the target path, its pixel
    dimensions are read from disk and used instead of re-rendering.
    The DPI of an existing PNG is not validated; delete `pages/` to
    force a clean re-render at a new DPI.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file():
        raise AudiobookIshError(f"PDF not found: {pdf_path}")
    if dpi <= 0:
        raise AudiobookIshError(f"DPI must be positive, got {dpi}")

    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise AudiobookIshError(f"Could not open PDF {pdf_path}: {exc}") from exc

    try:
        page_count = len(doc)
        if page_count == 0:
            raise AudiobookIshError(f"PDF has no pages: {pdf_path}")

        n_digits = max(3, len(str(page_count)))
        n_new = 0
        n_resumed = 0
        infos: list[PageInfo] = []

        for i, page in enumerate(doc, start=1):
            filename = _page_filename(i, n_digits)
            png_path = pages_dir / filename
            pdf_w = float(page.rect.width)
            pdf_h = float(page.rect.height)

            if png_path.is_file():
                try:
                    cached = pymupdf.Pixmap(str(png_path))
                    width_px, height_px = cached.width, cached.height
                    cached = None  # release memory
                    n_resumed += 1
                except Exception:
                    # Corrupt cache; re-render.
                    pix = page.get_pixmap(dpi=dpi)
                    pix.save(str(png_path))
                    width_px, height_px = pix.width, pix.height
                    n_new += 1
            else:
                pix = page.get_pixmap(dpi=dpi)
                pix.save(str(png_path))
                width_px, height_px = pix.width, pix.height
                n_new += 1

            info = PageInfo(
                number=i,
                image=f"pages/{filename}",
                width_px=width_px,
                height_px=height_px,
                pdf_width_pt=pdf_w,
                pdf_height_pt=pdf_h,
            )
            infos.append(info)
            if on_progress is not None:
                on_progress(i, info)
    finally:
        doc.close()

    log.info(
        "Rendered %d pages to %s (%d new, %d resumed) @ %d DPI",
        len(infos), pages_dir, n_new, n_resumed, dpi,
    )
    return infos
