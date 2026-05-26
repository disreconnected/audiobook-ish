"""Tests for chapter heading detection."""

from __future__ import annotations

from audiobook_ish import Sentence
from audiobook_ish.chapters import detect_chapters


def _sentence(id: int, text: str, page: int = 1, start: float | None = None) -> Sentence:
    return Sentence(id=id, text=text, page=page, bbox=(0, 0, 1, 1), start_sec=start, end_sec=None)


def test_emits_chapters_but_not_part_or_book_lines() -> None:
    sentences = [
        _sentence(0, "Translator's Preface."),
        _sentence(1, "PART I"),
        _sentence(2, "Some narrative."),
        _sentence(3, "CHAPTER II", page=5, start=3.0),
        _sentence(4, "BOOK TWO"),  # ignored because numeral is not roman/digits
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Part I - Chapter II"]
    assert chapters[0].sentence_id == 3


def test_ignores_non_heading_words() -> None:
    sentences = [
        _sentence(0, "This is definitely not a heading because it's too long."),
        _sentence(1, "Chapterhouse"),
        _sentence(2, "partially done"),
    ]
    assert detect_chapters(sentences) == []


def test_chapters_qualified_by_part_so_same_number_repeats() -> None:
    sentences = [
        _sentence(0, "PART I"),
        _sentence(1, "CHAPTER I"),
        _sentence(2, "CHAPTER II"),
        _sentence(3, "PART II"),
        _sentence(4, "CHAPTER I"),
        _sentence(5, "CHAPTER II"),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == [
        "Part I - Chapter I",
        "Part I - Chapter II",
        "Part II - Chapter I",
        "Part II - Chapter II",
    ]


def test_dedups_same_qualified_chapter() -> None:
    sentences = [
        _sentence(0, "PART I"),
        _sentence(1, "CHAPTER I"),
        _sentence(2, "CHAPTER I"),  # repeated heading from TOC/first page
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Part I - Chapter I"]


def test_part_only_does_not_appear_in_chapter_list() -> None:
    chapters = detect_chapters([_sentence(0, "PART I")])
    assert chapters == []


def test_epilogue_emitted_as_its_own_anchor_and_sets_context() -> None:
    sentences = [
        _sentence(0, "EPILOGUE"),
        _sentence(1, "CHAPTER I"),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Epilogue", "Epilogue - Chapter I"]


def test_detects_heading_when_sentence_has_trailing_prose() -> None:
    sentences = [
        _sentence(
            0,
            "Crime and Punishment Part I Chapter I On an exceptionally hot evening...",
            page=7,
        ),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Part I - Chapter I"]


def test_preserves_roman_numeral_case() -> None:
    sentences = [_sentence(0, "CHAPTER IV") , _sentence(1, "CHAPTER XII")]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Chapter IV", "Chapter XII"]
