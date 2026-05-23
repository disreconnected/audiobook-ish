# context.md — for AI agents

This file is the orientation doc for LLM agents working on this repo. Read it before doing anything non-trivial.

## What this project is

`audiobook-ish` converts a PDF into a **page-synced audiobook**: an MP3 plus a static HTML player that highlights the current sentence on the rendered PDF page while the audio plays.

The user's mental model: **"Speechify, but local, free, and hackable."**

## What "done" looks like

A user runs one command:

```
audiobook-ish build book.pdf --out examples/book
```

…and gets a folder they can zip, copy to any machine, open `player.html`, and use offline. No backend, no subscription, no telemetry.

## Repo layout

```
audiobook-ish/
├── README.md             # user-facing
├── context.md            # this file
├── PLAN.md               # milestone breakdown, design decisions, open questions
├── pyproject.toml
├── audiobook_ish/        # the Python package
│   ├── extract.py        # PDF → list[Sentence] (text + page + bbox)
│   ├── synthesize.py     # Kokoro TTS, per-sentence, resumable
│   ├── manifest.py       # build manifest.json from sentence durations
│   ├── render.py         # PDF pages → PNGs at fixed DPI
│   ├── combine.py        # concat sentence WAVs → single MP3 via ffmpeg
│   └── cli/__main__.py   # `audiobook-ish build|render|player` subcommands
├── player/               # static web player (HTML + vanilla JS + CSS)
│   ├── index.html
│   ├── player.js
│   ├── player.css
│   └── assets/
├── examples/             # generated outputs live here (gitignored)
├── tests/
├── docs/
├── scripts/              # dev/maintenance scripts
└── legacy/               # the original chunk-level prototype, kept for reference
```

## Core data model

Everything revolves around a `Sentence`:

```python
@dataclass
class Sentence:
    id: int                  # 0-based, monotonic across whole book
    text: str                # ASCII-clean, ready for TTS
    page: int                # 1-based PDF page number
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF coords on `page`
    start_sec: float | None  # filled in after synthesis
    end_sec: float | None    # filled in after synthesis
```

`manifest.json` is just `{"sentences": [Sentence, ...], "page_count": N, "duration_sec": D, "voice": "af_nicole", "speed": 1.2, "sample_rate": 24000}`.

The player only ever reads `manifest.json` + the MP3 + the page PNGs. **Keep the manifest schema stable** — changes are breaking.

## Conventions

- **Resumability is mandatory.** Anything slow (synthesis, page rendering) must skip work whose output already exists on disk. Use the per-sentence WAV file (`sentences/sent_00000.wav`) as the source of truth for "is this done".
- **Text cleaning is centralized** in `extract.clean_for_tts()`. All non-ASCII transliteration, smart-quote replacement, and boilerplate stripping happens there — never in `synthesize`.
- **Coordinates.** PDF coords from PyMuPDF are top-left origin, in PDF points (1/72 in). When rendering pages to PNG we pick a single DPI (default 150) and store the scale factor in the manifest so the player can map PDF bbox → pixel coords.
- **No global state.** Pass config/paths explicitly. Functions take `Path` objects, not strings.
- **Logging.** Use the stdlib `logging` module, never `print`, except in `cli/__main__.py`.
- **Errors that need user action** raise `AudiobookIshError` (defined in `audiobook_ish/__init__.py`).

## Things that have already burned us

1. **PyMuPDF on Windows extracts some glyphs as private-use Unicode (U+F600–F6FF).** Strip these in `clean_for_tts()`.
2. **Smart quotes / em dashes / ellipsis must be normalized to ASCII** or Kokoro mispronounces or skips them. See `legacy/generate_audiobook.py::clean_text` for the working ruleset.
3. **Kokoro's `KPipeline(text, voice, speed)` yields multiple `(graphemes, phonemes, audio)` tuples per input** — it splits internally. For sentence-level timing, **feed one sentence at a time** and concatenate the yielded audios, recording the total duration as that sentence's duration.
4. **Hyphenated words at PDF line breaks** (`hard-\nworking`) must be rejoined before sentence splitting, or you get half-words and broken sentence boundaries.
5. **The user's ffmpeg is at a Winget path**, not on `PATH`. Default to `shutil.which("ffmpeg")` but allow override via `AUDIOBOOK_ISH_FFMPEG` env var.

## Workflow expectations

- **Plan before coding.** For any non-trivial change, update `PLAN.md` first.
- **One milestone at a time.** Don't jump ahead. See `PLAN.md` for current milestone.
- **Test on a small PDF first** (`tests/fixtures/tiny.pdf`, a few pages) before running anything on the full ~750-page test book.
- **Never commit anything in `examples/`** (it's gitignored). Generated artifacts go there.
- **Never commit anything in `legacy/`** that wasn't already there. That folder is frozen reference.

## Tools you have

- `pymupdf` (also exposed as `fitz`) for PDF read + render
- `kokoro` (`KPipeline`) for TTS
- `soundfile` + `numpy` for WAV I/O
- `ffmpeg` (subprocess) for WAV → MP3
- Browser-only for the player: no build step, no framework, vanilla JS

## Style

- Functions over classes unless state is genuinely shared.
- Type hints everywhere in `audiobook_ish/`.
- Docstrings: one-line summary, then args/returns only if non-obvious.
- Keep modules under ~200 lines. Split when they grow.

## When in doubt

Open an issue-style note in `PLAN.md` under **"Open questions"** instead of guessing.
