"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pymupdf
import pytest


@pytest.fixture
def tiny_pdf(tmp_path: Path) -> Path:
    """A two-page PDF with known text content for extraction tests.

    Page 1:
        Hello world. This is the first sentence.
        And another sentence on page one.
    Page 2:
        Second page starts here. End of book.
    """
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text((72, 100), "Hello world. This is the first sentence.", fontsize=12)
    page1.insert_text((72, 130), "And another sentence on page one.", fontsize=12)

    page2 = doc.new_page()
    page2.insert_text((72, 100), "Second page starts here.", fontsize=12)
    page2.insert_text((72, 130), "End of book.", fontsize=12)

    out = tmp_path / "tiny.pdf"
    doc.save(out)
    doc.close()
    return out


@pytest.fixture
def hyphenated_pdf(tmp_path: Path) -> Path:
    """A PDF that intentionally line-breaks across a hyphen."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "His parents were very hard-", fontsize=12)
    page.insert_text((72, 130), "working and religious. The end.", fontsize=12)
    out = tmp_path / "hyphen.pdf"
    doc.save(out)
    doc.close()
    return out


@pytest.fixture
def real_pdf() -> Path:
    """Path to a real-world PDF for integration testing.

    Skips the test if AUDIOBOOK_ISH_TEST_PDF env var isn't set, so CI can
    run without the (large, copyrighted) fixture.
    """
    env = os.environ.get("AUDIOBOOK_ISH_TEST_PDF")
    if not env:
        pytest.skip("Set AUDIOBOOK_ISH_TEST_PDF to a PDF path to run this test")
    path = Path(env)
    if not path.is_file():
        pytest.skip(f"AUDIOBOOK_ISH_TEST_PDF points to a missing file: {path}")
    return path
