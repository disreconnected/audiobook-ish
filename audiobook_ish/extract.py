"""PDF → list[Sentence].

Responsible for:
- opening the PDF with PyMuPDF,
- pulling text + bounding boxes per page,
- rejoining hyphenated line breaks,
- stripping boilerplate (headers, footers, page numbers, glyph markers),
- ASCII-cleaning for TTS,
- splitting into sentences with page-anchored bboxes.

See PLAN.md M1 for the acceptance criteria.
"""

from __future__ import annotations

from pathlib import Path

from . import Sentence


def extract_sentences(pdf_path: Path) -> list[Sentence]:
    """Extract narration-ready sentences with page + bbox info.

    TODO(M1): implement.
    """
    raise NotImplementedError("M1 not yet implemented — see PLAN.md")


def clean_for_tts(raw: str) -> str:
    """Normalize raw PDF text so Kokoro pronounces it correctly.

    TODO(M1): port the ruleset from legacy/generate_audiobook.py and add tests.
    """
    raise NotImplementedError("M1 not yet implemented — see PLAN.md")
