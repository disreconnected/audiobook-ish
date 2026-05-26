"""Tests for chapter heading detection."""

from __future__ import annotations

from audiobook_ish import Sentence
from audiobook_ish.chapters import detect_chapters


def test_detects_common_heading_patterns() -> None:
    sentences = [
        Sentence(id=0, text="Translator's Preface.", page=1, bbox=(0, 0, 1, 1), start_sec=0.0, end_sec=1.0),
        Sentence(id=1, text="PART I", page=2, bbox=(0, 0, 1, 1), start_sec=1.0, end_sec=1.2),
        Sentence(id=2, text="Some narrative.", page=2, bbox=(0, 0, 1, 1), start_sec=1.2, end_sec=3.0),
        Sentence(id=3, text="CHAPTER II", page=5, bbox=(0, 0, 1, 1), start_sec=3.0, end_sec=3.2),
        Sentence(id=4, text="PART TWO", page=20, bbox=(0, 0, 1, 1), start_sec=10.0, end_sec=10.2),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Chapter Ii"]
    assert [c.sentence_id for c in chapters] == [3]


def test_ignores_long_or_non_heading_lines() -> None:
    sentences = [
        Sentence(id=0, text="This is definitely not a heading because it's too long and descriptive.", page=1, bbox=(0, 0, 1, 1)),
        Sentence(id=1, text="Chapterhouse", page=2, bbox=(0, 0, 1, 1)),
        Sentence(id=2, text="partially done", page=3, bbox=(0, 0, 1, 1)),
    ]
    chapters = detect_chapters(sentences)
    assert chapters == []


def test_deduplicates_repeated_headings() -> None:
    sentences = [
        Sentence(id=0, text="CHAPTER I", page=1, bbox=(0, 0, 1, 1)),
        Sentence(id=1, text="CHAPTER I", page=2, bbox=(0, 0, 1, 1)),
        Sentence(id=2, text="CHAPTER II", page=3, bbox=(0, 0, 1, 1)),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Chapter I", "Chapter Ii"]


def test_detects_heading_prefix_when_sentence_has_trailing_text() -> None:
    sentences = [
        Sentence(id=0, text="Chapter IV H is mother's letter had been a torture to him.", page=10, bbox=(0, 0, 1, 1)),
    ]
    chapters = detect_chapters(sentences)
    assert len(chapters) == 1
    assert chapters[0].title == "Chapter Iv"


def test_detects_multiple_headings_in_same_sentence() -> None:
    sentences = [
        Sentence(
            id=0,
            text="Crime and Punishment Part I Chapter I On an exceptionally hot evening...",
            page=7,
            bbox=(0, 0, 1, 1),
        ),
    ]
    chapters = detect_chapters(sentences)
    assert [c.title for c in chapters] == ["Chapter I"]
