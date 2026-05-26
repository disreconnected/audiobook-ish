"""Lightweight chapter heading detection for sentence streams."""

from __future__ import annotations

import re

from . import ChapterInfo, Sentence

_ROMAN = r"[IVXLCDM]+"
_NUM = r"\d+"
_HEADING_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"(CHAPTER)\s+({_ROMAN}|{_NUM})\b", re.IGNORECASE),
)

def detect_chapters(sentences: list[Sentence]) -> list[ChapterInfo]:
    """Infer chapter anchors from heading-like short sentences.

    Heuristic:
    - sentence text must begin with one of the known heading forms
      (`PART II`, `CHAPTER 3`, etc.); extra text after the heading is allowed
      because extraction may merge headings with adjacent text.
    - deduplicate exact repeated headings.
    """
    out: list[ChapterInfo] = []
    seen_titles: set[str] = set()

    for s in sentences:
        text = (s.text or "").strip()
        if not text:
            continue
        headings = _extract_heading_tokens(text)
        if not headings:
            continue
        for heading in headings:
            title = _normalize_title(heading)
            if title in seen_titles:
                continue
            seen_titles.add(title)
            out.append(
                ChapterInfo(
                    title=title,
                    sentence_id=s.id,
                    page=s.page,
                    start_sec=s.start_sec,
                )
            )
    return out


def _normalize_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return text.title()


def _extract_heading_tokens(text: str) -> list[str]:
    """Return heading tokens found in reading order.

    We search anywhere in the sentence because PDF extraction often merges
    structural headings into surrounding prose, e.g.
    "Crime and Punishment Part I Chapter I ..."
    """
    text = text.strip()
    found: list[tuple[int, str]] = []
    for pattern in _HEADING_TOKEN_PATTERNS:
        for m in pattern.finditer(text):
            found.append((m.start(), f"{m.group(1)} {m.group(2)}"))
    found.sort(key=lambda t: t[0])
    ordered: list[str] = []
    seen_local: set[str] = set()
    for _, token in found:
        norm = _normalize_title(token)
        if norm in seen_local:
            continue
        seen_local.add(norm)
        ordered.append(token)
    return ordered
