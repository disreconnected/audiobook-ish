"""Command-line entry point for audiobook-ish."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from audiobook_ish import AudiobookIshError, Sentence
from audiobook_ish.chapters import detect_chapters
from audiobook_ish.combine import combine
from audiobook_ish.extract import extract_sentences
from audiobook_ish.manifest import build_manifest, write_manifest, write_manifest_js
from audiobook_ish.player_bundle import bundle_player
from audiobook_ish.render import render_pages
from audiobook_ish.synthesize import DEFAULT_SAMPLE_RATE, synthesize

log = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _sentence_to_dict(s: Sentence) -> dict:
    return {
        "id": s.id,
        "text": s.text,
        "page": s.page,
        "bbox": list(s.bbox),
        "start_sec": s.start_sec,
        "end_sec": s.end_sec,
    }


def _dict_to_sentence(d: dict) -> Sentence:
    return Sentence(
        id=int(d["id"]),
        text=str(d["text"]),
        page=int(d["page"]),
        bbox=tuple(float(x) for x in d["bbox"]),  # type: ignore[arg-type]
        start_sec=float(d["start_sec"]) if d.get("start_sec") is not None else None,
        end_sec=float(d["end_sec"]) if d.get("end_sec") is not None else None,
    )


def _write_sentences_json(path: Path, source_pdf: Path, sentences: list[Sentence]) -> None:
    payload = {
        "source_pdf": str(source_pdf),
        "count": len(sentences),
        "sentences": [_sentence_to_dict(s) for s in sentences],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_sentences_json(path: Path) -> tuple[Path | None, list[Sentence]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    src_raw = payload.get("source_pdf")
    source_pdf = Path(src_raw) if src_raw else None
    sentences = [_dict_to_sentence(s) for s in payload["sentences"]]
    return source_pdf, sentences


def _write_manifest_pair(manifest, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest, out_dir / "manifest.json")
    write_manifest_js(manifest, out_dir / "manifest.js")


def _cmd_extract(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    sentences = extract_sentences(pdf)
    if args.max_sentences is not None:
        sentences = sentences[: args.max_sentences]
        # Re-id after truncation to keep contiguous sentence IDs.
        for i, s in enumerate(sentences):
            s.id = i
    _write_sentences_json(out, pdf, sentences)
    print(f"Extracted {len(sentences)} sentences -> {out.resolve()}")
    return 0


def _cmd_synthesize(args: argparse.Namespace) -> int:
    sentences_json = Path(args.sentences)
    out_dir = Path(args.out)
    source_pdf, sentences = _load_sentences_json(sentences_json)
    if args.max_sentences is not None:
        sentences = sentences[: args.max_sentences]
        for i, s in enumerate(sentences):
            s.id = i

    manifest_every = max(1, int(args.checkpoint_every))
    src_name = source_pdf.name if source_pdf is not None else "unknown.pdf"

    def on_progress(idx: int, _sentence: Sentence) -> None:
        if (idx + 1) % manifest_every != 0 and (idx + 1) != len(sentences):
            return
        partial = build_manifest(
            source_pdf=src_name,
            voice=args.voice,
            speed=args.speed,
            sample_rate=args.sample_rate,
            pages=[],
            sentences=sentences,
            chapters=detect_chapters(sentences),
        )
        _write_manifest_pair(partial, out_dir)

    synthesize(
        sentences=sentences,
        output_dir=out_dir,
        voice=args.voice,
        speed=args.speed,
        sample_rate=args.sample_rate,
        on_progress=on_progress,
    )
    _write_sentences_json(out_dir / "sentences.json", source_pdf or Path(src_name), sentences)
    print(f"Synthesized {len(sentences)} sentences -> {out_dir.resolve() / 'sentences'}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    pages = render_pages(pdf, out, dpi=args.dpi)
    print(f"Rendered {len(pages)} pages -> {(out / 'pages').resolve()}")
    return 0


def _cmd_combine(args: argparse.Namespace) -> int:
    sentences_dir = Path(args.sentences_dir)
    out_mp3 = Path(args.out)
    combine(
        sentences_dir=sentences_dir,
        output_mp3=out_mp3,
        bitrate=args.bitrate,
        ffmpeg_path=args.ffmpeg,
    )
    print(f"Combined sentence WAVs -> {out_mp3.resolve()}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sentences = extract_sentences(pdf)
    if args.max_sentences is not None:
        sentences = sentences[: args.max_sentences]
        for i, s in enumerate(sentences):
            s.id = i
    _write_sentences_json(out / "sentences.json", pdf, sentences)
    print(f"[1/5] Extracted {len(sentences)} sentences")

    checkpoint_every = max(1, int(args.checkpoint_every))

    def on_progress(idx: int, _sentence: Sentence) -> None:
        if (idx + 1) % checkpoint_every != 0 and (idx + 1) != len(sentences):
            return
        partial = build_manifest(
            source_pdf=pdf.name,
            voice=args.voice,
            speed=args.speed,
            sample_rate=args.sample_rate,
            pages=[],
            sentences=sentences,
            chapters=detect_chapters(sentences),
        )
        _write_manifest_pair(partial, out)

    synthesize(
        sentences=sentences,
        output_dir=out,
        voice=args.voice,
        speed=args.speed,
        sample_rate=args.sample_rate,
        on_progress=on_progress,
    )
    _write_sentences_json(out / "sentences.json", pdf, sentences)
    print("[2/5] Synthesized sentence WAVs")

    pages = render_pages(pdf, out, dpi=args.dpi)
    print(f"[3/5] Rendered {len(pages)} pages")

    combine(out / "sentences", out / "audiobook.mp3", bitrate=args.bitrate, ffmpeg_path=args.ffmpeg)
    print("[4/5] Combined WAVs -> audiobook.mp3")

    manifest = build_manifest(
        source_pdf=pdf.name,
        voice=args.voice,
        speed=args.speed,
        sample_rate=args.sample_rate,
        pages=pages,
        sentences=sentences,
        chapters=detect_chapters(sentences),
    )
    _write_manifest_pair(manifest, out)
    bundle_player(out)
    print("[5/5] Wrote manifest + bundled player")
    print(f"Done: {out.resolve() / 'player.html'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audiobook-ish",
        description="Generate page-synced audiobooks from PDFs using Kokoro TTS.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable INFO logging")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Run the full pipeline end-to-end")
    build.add_argument("pdf")
    build.add_argument("--out", required=True)
    build.add_argument("--voice", default="af_nicole")
    build.add_argument("--speed", type=float, default=1.2)
    build.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    build.add_argument("--dpi", type=int, default=150)
    build.add_argument("--bitrate", default="128k")
    build.add_argument("--ffmpeg", default=None, help="Explicit ffmpeg binary path")
    build.add_argument("--checkpoint-every", type=int, default=100)
    build.add_argument("--max-sentences", type=int, default=None, help="Dev/testing limiter")

    extract = sub.add_parser("extract", help="Extract sentences from a PDF into JSON")
    extract.add_argument("pdf")
    extract.add_argument("--out", required=True, help="Output JSON path")
    extract.add_argument("--max-sentences", type=int, default=None, help="Dev/testing limiter")

    synth = sub.add_parser("synthesize", help="Synthesize sentence JSON into WAVs")
    synth.add_argument("sentences", help="Path to sentences JSON produced by extract/build")
    synth.add_argument("--out", required=True)
    synth.add_argument("--voice", default="af_nicole")
    synth.add_argument("--speed", type=float, default=1.2)
    synth.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    synth.add_argument("--checkpoint-every", type=int, default=100)
    synth.add_argument("--max-sentences", type=int, default=None, help="Dev/testing limiter")

    render = sub.add_parser("render", help="Render PDF pages into PNGs")
    render.add_argument("pdf")
    render.add_argument("--out", required=True)
    render.add_argument("--dpi", type=int, default=150)

    combine_cmd = sub.add_parser("combine", help="Combine sentence WAVs into one MP3")
    combine_cmd.add_argument("sentences_dir", help="Directory with sent_*.wav files")
    combine_cmd.add_argument("--out", required=True)
    combine_cmd.add_argument("--bitrate", default="128k")
    combine_cmd.add_argument("--ffmpeg", default=None, help="Explicit ffmpeg binary path")

    bundle = sub.add_parser("bundle-player", help="Copy static player assets into an output folder")
    bundle.add_argument("out")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.cmd == "build":
            return _cmd_build(args)
        if args.cmd == "extract":
            return _cmd_extract(args)
        if args.cmd == "synthesize":
            return _cmd_synthesize(args)
        if args.cmd == "render":
            return _cmd_render(args)
        if args.cmd == "combine":
            return _cmd_combine(args)
        if args.cmd == "bundle-player":
            bundle_player(Path(args.out))
            print(f"Player bundled in: {Path(args.out).resolve()}")
            return 0
    except AudiobookIshError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
