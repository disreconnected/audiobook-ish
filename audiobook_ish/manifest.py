"""Build and persist manifest.json — the contract between generator and player.

See PLAN.md M2/M3 and the schema section.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import MANIFEST_SCHEMA_VERSION, Manifest, PageInfo, Sentence


def build_manifest(
    source_pdf: str,
    voice: str,
    speed: float,
    sample_rate: int,
    pages: list[PageInfo],
    sentences: list[Sentence],
    page_count: int | None = None,
) -> Manifest:
    """Assemble a Manifest from synthesis + render outputs."""
    duration = sentences[-1].end_sec if sentences and sentences[-1].end_sec else 0.0
    inferred_page_count = page_count
    if inferred_page_count is None:
        inferred_page_count = len(pages) if pages else max((s.page for s in sentences), default=0)
    return Manifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        source_pdf=source_pdf,
        voice=voice,
        speed=speed,
        sample_rate=sample_rate,
        page_count=int(inferred_page_count),
        duration_sec=float(duration),
        pages=pages,
        sentences=sentences,
    )


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Serialize the manifest to JSON. Bbox tuples become arrays."""
    payload = manifest_to_dict(manifest)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_manifest_js(manifest: Manifest, path: Path) -> None:
    """Write a JS bootstrap file for file:// playback.

    The player checks `window.AUDIOBOOK_ISH_MANIFEST` before falling back to
    `fetch('manifest.json')`, so local file playback can work without CORS.
    """
    payload = manifest_to_dict(manifest)
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    path.write_text(f"window.AUDIOBOOK_ISH_MANIFEST={data};\n", encoding="utf-8")


def manifest_to_dict(manifest: Manifest) -> dict:
    """Convert manifest dataclasses into a JSON-serializable dictionary."""
    payload = asdict(manifest)
    payload["sentences"] = [_sentence_to_dict(s) for s in manifest.sentences]
    payload["pages"] = [asdict(p) for p in manifest.pages]
    return payload


def _sentence_to_dict(s: Sentence) -> dict:
    return {
        "id": s.id,
        "text": s.text,
        "page": s.page,
        "bbox": list(s.bbox),
        "start_sec": s.start_sec,
        "end_sec": s.end_sec,
    }
