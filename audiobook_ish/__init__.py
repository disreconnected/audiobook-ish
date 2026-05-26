"""audiobook-ish — generate page-synced audiobooks from PDFs using Kokoro TTS."""

from dataclasses import dataclass, field

__version__ = "0.1.0"

MANIFEST_SCHEMA_VERSION = 1


class AudiobookIshError(Exception):
    """Raised for errors that require user action (bad PDF, missing ffmpeg, etc.)."""


@dataclass
class Sentence:
    """A single sentence of narration with its source-page anchor."""

    id: int
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    start_sec: float | None = None
    end_sec: float | None = None

    @property
    def duration_sec(self) -> float | None:
        if self.start_sec is None or self.end_sec is None:
            return None
        return self.end_sec - self.start_sec


@dataclass
class PageInfo:
    """Pixel dimensions of a rendered PDF page, plus its PDF-point size."""

    number: int
    image: str
    width_px: int
    height_px: int
    pdf_width_pt: float
    pdf_height_pt: float


@dataclass
class ChapterInfo:
    """Detected chapter anchor for quick navigation in the player."""

    title: str
    sentence_id: int
    page: int
    start_sec: float | None = None


@dataclass
class Manifest:
    """The full manifest the player consumes. See PLAN.md for schema."""

    source_pdf: str
    voice: str
    speed: float
    sample_rate: int
    page_count: int
    duration_sec: float
    pages: list[PageInfo] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)
    chapters: list[ChapterInfo] = field(default_factory=list)
    schema_version: int = MANIFEST_SCHEMA_VERSION


__all__ = [
    "AudiobookIshError",
    "ChapterInfo",
    "MANIFEST_SCHEMA_VERSION",
    "Manifest",
    "PageInfo",
    "Sentence",
    "__version__",
]
