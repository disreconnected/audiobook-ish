"""Render PDF pages to PNGs at a fixed DPI, record their pixel dims.

See PLAN.md M3.
"""

from __future__ import annotations

from pathlib import Path

from . import PageInfo


def render_pages(pdf_path: Path, output_dir: Path, dpi: int = 150) -> list[PageInfo]:
    """Render every PDF page to `output_dir / "pages" / page_NNN.png`.

    Returns a list of PageInfo entries (pixel + PDF-point dimensions) so the
    manifest can record the scale factor for bbox → pixel conversion.

    TODO(M3): implement.
    """
    raise NotImplementedError("M3 not yet implemented — see PLAN.md")
