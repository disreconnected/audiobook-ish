"""Chapter-heading detection for sentence streams.

The detector walks sentences left-to-right and tracks the current "part"
context so that chapter labels can be disambiguated across multi-part
books (Crime and Punishment, for example, has six parts each containing
their own ``CHAPTER I``).

Output rules:

* ``PART N`` and ``BOOK N`` markers update the current part context but
  are NOT emitted as chapter entries on their own.
* ``EPILOGUE`` sets the context to "Epilogue" and is emitted as its own
  chapter entry.
* ``CHAPTER N`` is emitted as ``"{context} - Chapter N"`` when a part
  context is set, otherwise as ``"Chapter N"``.
* Each unique (context, chapter-number) pair is emitted at most once;
  PDF extraction often surfaces the same heading twice (TOC + first page
  of the chapter).
"""

from __future__ import annotations

import re

from . import ChapterInfo, Sentence

_ROMAN = r"[IVXLCDM]+"
_NUM = r"\d+"

# Single token regex so we can iterate headings in reading order within a
# sentence. The match is case-sensitive and only accepts UPPER ("PART") or
# Title ("Part") casing for the keyword: lowercase prose like "book in his
# hand" must not register as a heading. Roman numerals must be uppercase
# for the same reason.
_HEADING_REGEX = re.compile(
    rf"\b(?P<kind>PART|Part|BOOK|Book|CHAPTER|Chapter|EPILOGUE|Epilogue)\b"
    rf"(?:\s+(?P<num>{_ROMAN}|{_NUM}))?"
)
_ROMAN_ONLY = re.compile(r"^[IVXLCDM]+$")


def detect_chapters(sentences: list[Sentence]) -> list[ChapterInfo]:
    """Infer chapter anchors from a sentence stream.

    See module docstring for the labelling rules.
    """
    out: list[ChapterInfo] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    current_part: str | None = None

    for s in sentences:
        text = (s.text or "").strip()
        if not text:
            continue
        for m in _HEADING_REGEX.finditer(text):
            kind = m.group("kind").upper()
            num = m.group("num")
            if kind in ("PART", "BOOK"):
                if num is None:
                    continue
                current_part = f"{kind.capitalize()} {_normalize_numeral(num)}"
            elif kind == "EPILOGUE":
                current_part = "Epilogue"
                key: tuple[str | None, str | None] = ("Epilogue", None)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                out.append(
                    ChapterInfo(
                        title="Epilogue",
                        sentence_id=s.id,
                        page=s.page,
                        start_sec=s.start_sec,
                    )
                )
            elif kind == "CHAPTER":
                if num is None:
                    continue
                numeral = _normalize_numeral(num)
                chap_label = f"Chapter {numeral}"
                title = f"{current_part} - {chap_label}" if current_part else chap_label
                key = (current_part, numeral)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                out.append(
                    ChapterInfo(
                        title=title,
                        sentence_id=s.id,
                        page=s.page,
                        start_sec=s.start_sec,
                    )
                )
    return out


def _normalize_numeral(s: str) -> str:
    """Upper-case Roman numerals, leave Arabic digits alone."""
    if _ROMAN_ONLY.match(s):
        return s.upper()
    return s
