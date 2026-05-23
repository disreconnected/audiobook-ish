"""Tests for audiobook_ish.extract."""

from __future__ import annotations

from pathlib import Path

import pytest

from audiobook_ish import AudiobookIshError, Sentence
from audiobook_ish.extract import (
    _is_boilerplate,
    clean_for_tts,
    extract_sentences,
)


class TestCleanForTts:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Smart quotes -> ASCII
            ("\u201cHello,\u201d he said.", '"Hello," he said.'),
            ("It\u2019s fine.", "It's fine."),
            # Em dash -> spoken pause
            ("Wait\u2014really?", "Wait -- really?"),
            # Ellipsis
            ("Well...", "Well..."),
            ("Well\u2026", "Well..."),
            # Accents -> bare letters
            ("na\u00efve fianc\u00e9e", "naive fiancee"),
            ("Morgenfr\u00fch", "Morgenfruh"),
            ("Svidriga\u00eflovs", "Svidrigailovs"),
            # Ligatures
            ("of\ufb01ce", "office"),
            ("\ufb02ag", "flag"),
            # Whitespace collapse
            ("  multiple    spaces  ", "multiple spaces"),
            # Zero-width and BOM removal
            ("text\u200bwith\ufeffinvisible", "textwithinvisible"),
            # Private-use glyphs stripped
            ("PUA\uf645junk", "PUAjunk"),
            # In-line hyphenated line breaks repaired
            ("very hard- working class", "very hardworking class"),
            ("pre- existing condition", "preexisting condition"),
            # Legitimate compounds (Title-Cased second word) left intact
            ("Twenty- Five", "Twenty- Five"),
        ],
    )
    def test_known_inputs(self, raw: str, expected: str) -> None:
        assert clean_for_tts(raw) == expected

    def test_output_is_ascii_only(self) -> None:
        weird = "\u00a0\u2018\u201c\u2014\u2026\u00ef\ufb01\uf645"
        out = clean_for_tts(f"prefix {weird} suffix")
        assert all(ord(c) < 128 for c in out), out


class TestIsBoilerplate:
    @pytest.mark.parametrize("line", ["", "   ", "1", "42", "999", "\uf645\uf646"])
    def test_boilerplate(self, line: str) -> None:
        assert _is_boilerplate(line, page_number=10)

    @pytest.mark.parametrize(
        "line",
        [
            "Hello world.",
            "Chapter 1",
            "Page 42 of the manuscript",  # contains a number but not pure
            "A novel by someone",
        ],
    )
    def test_non_boilerplate(self, line: str) -> None:
        assert not _is_boilerplate(line, page_number=10)

    def test_planet_ebook_headers(self) -> None:
        assert _is_boilerplate("Free eBooks at Planet eBook.com", 1)
        assert _is_boilerplate("Download free eBooks of classic literature", 1)


class TestExtractSentences:
    def test_missing_pdf_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AudiobookIshError, match="not found"):
            extract_sentences(tmp_path / "nope.pdf")

    def test_tiny_pdf_basics(self, tiny_pdf: Path) -> None:
        sentences = extract_sentences(tiny_pdf)

        # We expect at least 4 sentences (one per sentence-terminator in the fixture).
        assert len(sentences) >= 4

        # Every sentence is a properly-typed Sentence with sane fields.
        for s in sentences:
            assert isinstance(s, Sentence)
            assert s.id >= 0
            assert s.text
            assert s.page >= 1
            assert len(s.bbox) == 4
            x0, y0, x1, y1 = s.bbox
            assert x0 < x1
            assert y0 < y1

        # IDs are contiguous and start at 0.
        assert [s.id for s in sentences] == list(range(len(sentences)))

        # Pages are monotonically non-decreasing in reading order.
        for a, b in zip(sentences, sentences[1:]):
            assert a.page <= b.page

    def test_tiny_pdf_page_assignments(self, tiny_pdf: Path) -> None:
        sentences = extract_sentences(tiny_pdf)
        pages_seen = {s.page for s in sentences}
        # Both pages should produce at least one sentence.
        assert 1 in pages_seen
        assert 2 in pages_seen
        # 'End of book.' must be assigned to page 2.
        end = next(s for s in sentences if "End of book" in s.text)
        assert end.page == 2

    def test_tiny_pdf_text_is_ascii(self, tiny_pdf: Path) -> None:
        sentences = extract_sentences(tiny_pdf)
        for s in sentences:
            assert all(ord(c) < 128 for c in s.text), s.text

    def test_hyphenated_line_break_is_rejoined(self, hyphenated_pdf: Path) -> None:
        sentences = extract_sentences(hyphenated_pdf)
        joined = " ".join(s.text for s in sentences)
        assert "hardworking" in joined
        assert "hard-working" not in joined
        assert "hard working" not in joined


class TestExtractSentencesIntegration:
    """Heavyweight tests against a real book. Opt-in via env var."""

    def test_real_pdf_produces_many_sentences(self, real_pdf: Path) -> None:
        sentences = extract_sentences(real_pdf)
        assert len(sentences) > 100

        all_text = " ".join(s.text for s in sentences)
        non_ascii = sorted({c for c in all_text if ord(c) > 127})
        assert not non_ascii, f"non-ASCII chars leaked through: {non_ascii}"

        # Pages monotonically non-decreasing.
        for a, b in zip(sentences, sentences[1:]):
            assert a.page <= b.page

        # Every bbox is well-formed.
        for s in sentences:
            x0, y0, x1, y1 = s.bbox
            assert x0 < x1 and y0 < y1, (s.id, s.bbox)
