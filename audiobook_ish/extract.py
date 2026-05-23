"""PDF -> list[Sentence].

Pipeline per PDF:
    1. For each page, pull every text line with its bbox (skip boilerplate).
    2. Clean each line for TTS (ASCII-only, smart-quote normalization, etc).
    3. Concatenate cleaned lines into a single corpus, joining hyphenated
       line breaks with no space, ordinary line breaks with a single space.
       Keep a parallel list of (corpus_start, corpus_end, page, bbox) per line.
    4. Split the corpus on sentence terminators.
    5. For each sentence, find every line whose corpus range overlaps it.
       The sentence's page is the page of its *last* overlapping line; bbox is
       the union of bboxes of overlapping lines on that page.

The hyphenation handling intentionally happens before cleaning so that a
line ending in 'hard-' gets joined to 'working' as 'hardworking' (not
'hard working') the same way a human reader would resolve it.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from . import AudiobookIshError, Sentence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_CHARACTER_REPLACEMENTS: dict[str, str] = {
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u201e": '"',
    "\u201f": '"',
    "\u2014": " -- ",  # em dash -> spoken pause
    "\u2013": "-",     # en dash -> hyphen
    "\u2212": "-",     # minus sign
    "\u2026": "...",   # ellipsis
    "\u00a0": " ",     # NBSP
    "\u202f": " ",     # narrow NBSP
    "\u2009": " ",     # thin space
    "\u200b": "",      # zero-width space
    "\u200c": "",      # zero-width non-joiner
    "\u200d": "",      # zero-width joiner
    "\ufeff": "",      # BOM
    "\ufb00": "ff",    # ligatures
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}

_TTS_ALLOWED = re.compile(r"[^A-Za-z0-9 .,!?;:'\"()\-\[\]\n]")
_PUA_OR_CTRL = re.compile(r"[\uf600-\uf6ff\u0000-\u001f\u007f-\u009f]")
_MULTI_SPACE = re.compile(r"[ \t]+")

# Repair in-line hyphenated line breaks that PyMuPDF flattened onto one line,
# e.g. "hard- working" -> "hardworking". Only fires when the second token starts
# with a lowercase letter, leaving legitimate compounds like "Twenty- Five" alone.
_INLINE_HYPHEN_BREAK = re.compile(r"(\w)-\s+(?=[a-z])")


def clean_for_tts(raw: str) -> str:
    """Normalize raw PDF text so Kokoro pronounces it correctly.

    Returns ASCII-only text containing only characters that belong in a
    spoken novel: letters, digits, spaces, and `.,!?;:'"()-[]`.

    >>> clean_for_tts("\u201cHello,\u201d he said\u2014softly\u2026")
    '"Hello," he said -- softly...'
    >>> clean_for_tts("na\u00efve fianc\u00e9e")
    'naive fiancee'
    >>> clean_for_tts("  multiple    spaces  ")
    'multiple spaces'
    """
    text = raw
    for old, new in _CHARACTER_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = _PUA_OR_CTRL.sub("", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = _TTS_ALLOWED.sub(" ", text)
    text = _INLINE_HYPHEN_BREAK.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Boilerplate detection
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Download free eBooks of classic literature", re.IGNORECASE),
    re.compile(r"^novels at Planet eBook\.", re.IGNORECASE),
    re.compile(r"^Subscribe to our free eBooks blog", re.IGNORECASE),
    re.compile(r"^and email newsletter\.", re.IGNORECASE),
    re.compile(r"^Free eBooks at Planet eBook\.com$", re.IGNORECASE),
)

_PURE_DIGITS = re.compile(r"^\d{1,4}$")
_PURE_PUA = re.compile(r"^[\uf600-\uf6ff]+$")


def _is_boilerplate(line: str, page_number: int) -> bool:
    """True if `line` is a header/footer/page-number we should drop."""
    s = line.strip()
    if not s:
        return True
    if _PURE_DIGITS.match(s):
        # Pure-number lines are almost always page numbers.
        return True
    if _PURE_PUA.match(s):
        return True
    if any(p.search(s) for p in _BOILERPLATE_PATTERNS):
        return True
    return False


# ---------------------------------------------------------------------------
# Line + sentence extraction
# ---------------------------------------------------------------------------

Bbox = tuple[float, float, float, float]


@dataclass
class _LineSpan:
    """A single text line on a single page with its PDF-point bbox."""

    raw_text: str
    cleaned_text: str
    page: int
    bbox: Bbox


@dataclass
class _LineRange:
    """Where a line's cleaned text lives inside the corpus string."""

    start: int  # inclusive
    end: int   # exclusive
    line: _LineSpan


_HYPHEN_TAIL = re.compile(r"\w-$")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _extract_page_lines(page: "pymupdf.Page", page_number: int) -> list[_LineSpan]:
    """Pull every non-boilerplate text line from a single page."""
    out: list[_LineSpan] = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue  # not a text block
        for line in block.get("lines", []):
            raw = "".join(span.get("text", "") for span in line.get("spans", []))
            if _is_boilerplate(raw, page_number):
                continue
            cleaned = clean_for_tts(raw)
            if not cleaned:
                continue
            bbox = tuple(line["bbox"])  # type: ignore[assignment]
            if len(bbox) != 4:
                continue
            out.append(_LineSpan(raw_text=raw, cleaned_text=cleaned, page=page_number, bbox=bbox))
    return out


def _build_corpus(lines: list[_LineSpan]) -> tuple[str, list[_LineRange]]:
    """Concatenate cleaned line texts; track each line's char range in the corpus.

    Joins lines whose previous line ends with `\\w-` (hyphenated line break)
    without a separator and with the hyphen stripped, so 'hard-' + 'working'
    becomes 'hardworking'. Other line breaks become a single space.
    """
    pieces: list[str] = []
    ranges: list[_LineRange] = []
    cursor = 0
    prev_hyphenated = False

    for line in lines:
        text = line.cleaned_text
        if not text:
            continue

        if pieces and prev_hyphenated and text and text[0].isalpha():
            # Drop the trailing hyphen on the previous piece, then concat with no space.
            pieces[-1] = pieces[-1][:-1]
            last = ranges[-1]
            ranges[-1] = _LineRange(start=last.start, end=last.end - 1, line=last.line)
            cursor -= 1
            sep = ""
        elif pieces:
            sep = " "
        else:
            sep = ""

        pieces.append(sep + text)
        start = cursor + len(sep)
        end = start + len(text)
        ranges.append(_LineRange(start=start, end=end, line=line))
        cursor = end
        prev_hyphenated = bool(_HYPHEN_TAIL.search(text))

    corpus = "".join(pieces)
    return corpus, ranges


def _sentence_spans(corpus: str) -> list[tuple[int, int]]:
    """Return (start, end_exclusive) of each sentence in `corpus`."""
    starts = [0]
    ends: list[int] = []
    for match in _SENTENCE_BOUNDARY.finditer(corpus):
        ends.append(match.start())
        starts.append(match.end())
    ends.append(len(corpus))
    return list(zip(starts, ends))


def _union_bbox(boxes: list[Bbox]) -> Bbox:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def extract_sentences(pdf_path: Path) -> list[Sentence]:
    """Extract narration-ready sentences with page + bbox info.

    Raises AudiobookIshError if the PDF is empty or unreadable.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise AudiobookIshError(f"PDF not found: {pdf_path}")

    log.info("Opening PDF: %s", pdf_path)
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise AudiobookIshError(f"Could not open PDF {pdf_path}: {exc}") from exc

    try:
        all_lines: list[_LineSpan] = []
        for i, page in enumerate(doc, start=1):
            all_lines.extend(_extract_page_lines(page, i))
    finally:
        doc.close()

    if not all_lines:
        raise AudiobookIshError(f"No extractable text found in {pdf_path}")

    log.info("Extracted %d non-boilerplate lines from %s", len(all_lines), pdf_path.name)

    corpus, ranges = _build_corpus(all_lines)
    spans = _sentence_spans(corpus)

    sentences: list[Sentence] = []
    cursor = 0  # moving index into `ranges`

    for s_start, s_end in spans:
        # Strip whitespace from the sentence; recompute exact slice bounds.
        snippet = corpus[s_start:s_end]
        l_strip = len(snippet) - len(snippet.lstrip())
        r_strip = len(snippet) - len(snippet.rstrip())
        s_start += l_strip
        s_end -= r_strip
        text = corpus[s_start:s_end]
        if not text:
            continue

        # Advance cursor past lines that end at/before this sentence's start.
        while cursor < len(ranges) and ranges[cursor].end <= s_start:
            cursor += 1

        overlapping_lines: list[_LineSpan] = []
        j = cursor
        while j < len(ranges) and ranges[j].start < s_end:
            r = ranges[j]
            if r.end > s_start:
                overlapping_lines.append(r.line)
            j += 1

        if not overlapping_lines:
            continue

        last_page = overlapping_lines[-1].page
        last_page_lines = [ln for ln in overlapping_lines if ln.page == last_page]
        bbox = _union_bbox([ln.bbox for ln in last_page_lines])

        sentences.append(
            Sentence(
                id=len(sentences),
                text=text,
                page=last_page,
                bbox=bbox,
            )
        )

    log.info("Produced %d sentences", len(sentences))
    return sentences
