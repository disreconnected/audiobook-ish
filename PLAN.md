# PLAN.md

The roadmap. Treat this as a living document — update it before you change direction.

## Goal

Produce a single command that turns a PDF into an **offline, page-synced audiobook**:

- one MP3 of the full narration
- a static HTML player that highlights the current sentence on the rendered PDF page and in a scrollable text pane
- everything lives in one folder you can zip and move

## Design principles

1. **Local-first.** No network at runtime (after Kokoro model is cached).
2. **Resumable.** Long synthesis runs must survive interruption. Per-sentence WAV on disk = source of truth for "done".
3. **Stable manifest.** `manifest.json` is the contract between the generator and the player. Bump a schema version when it changes.
4. **No build step.** Player is one HTML file + one JS + one CSS, opened directly in any browser.
5. **One thing at a time.** Each module does one job. Pipelines are wired in `cli/__main__.py`.

## Pipeline

```
PDF
 │
 ▼  extract.py
[Sentence(id, text, page, bbox)]
 │
 ▼  synthesize.py    (resumable; writes sentences/sent_NNNNN.wav)
[Sentence(... start_sec, end_sec)]
 │
 ├──► combine.py     ─► audiobook.mp3
 ├──► render.py      ─► pages/page_NNN.png  (also writes page scale to manifest)
 └──► manifest.py    ─► manifest.json
                              │
                              ▼
                         player/  (copied to output dir, reads manifest.json)
```

## Output folder shape

```
examples/<book>/
├── audiobook.mp3
├── manifest.json
├── pages/
│   ├── page_001.png
│   └── ...
├── sentences/
│   ├── sent_00000.wav
│   └── ...
├── player.html         # copy of player/index.html
├── player.js
├── player.css
└── assets/             # icons, fonts (if any)
```

## Manifest schema (v1)

```json
{
  "schema_version": 1,
  "source_pdf": "crime-and-punishment.pdf",
  "voice": "af_nicole",
  "speed": 1.2,
  "sample_rate": 24000,
  "page_count": 767,
  "duration_sec": 83952.4,
  "pages": [
    { "number": 1, "image": "pages/page_001.png", "width_px": 1275, "height_px": 1650, "pdf_width_pt": 612, "pdf_height_pt": 792 }
  ],
  "sentences": [
    { "id": 0, "text": "Translator's Preface.", "page": 1, "bbox": [72.0, 120.5, 280.4, 138.2], "start_sec": 0.0, "end_sec": 1.4 }
  ]
}
```

The player computes a px-per-pt scale from `pages[i].width_px / pdf_width_pt` to position the highlight overlay.

## Milestones

### M0 — Scaffolding *(done in this commit)*

- Repo structure, README, context.md, PLAN.md, .gitignore, pyproject.toml
- Stub modules in `audiobook_ish/` with docstrings and TODOs
- Stub player files

### M1 — Sentence extraction with page tracking

**Goal:** `extract.extract_sentences(pdf_path) -> list[Sentence]` works on a small fixture PDF and the real Crime & Punishment PDF.

- Use `PyMuPDF`'s `page.get_text("dict")` to get per-block / per-span text with bboxes.
- Rejoin hyphenated line breaks within a page.
- Strip boilerplate lines (Planet eBook headers/footers, page numbers, glyph markers).
- Apply `clean_for_tts` ruleset (from `legacy/generate_audiobook.py`).
- Split into sentences with `re.split(r'(?<=[.!?])\s+', ...)`, but only within a single page span — multi-page sentences get bbox = union of their parts on the last page they end on (good enough for v1).
- Acceptance: on the fixture PDF, sentence count and page assignments match a hand-checked expected file.

### M2 — Per-sentence synthesis with manifest

**Goal:** `synthesize.synthesize(sentences, output_dir, voice, speed) -> list[Sentence]` produces `sentences/sent_NNNNN.wav` per sentence and fills in `start_sec` / `end_sec`.

- One `KPipeline` instance, reused across sentences.
- For each sentence: if WAV exists, read its length to recover duration; else synthesize, write, and concat any sub-segments Kokoro returns.
- Cumulative time tracking → `start_sec` / `end_sec`.
- Write a partial `manifest.json` after every N sentences so the player can be opened mid-run.
- Acceptance: kill the process mid-run, re-run, verify it picks up at the right sentence and total duration matches.

### M3 — Combine + render

**Goal:** Produce `audiobook.mp3` and `pages/page_NNN.png`.

- `combine.combine(sentences_dir, output_mp3, ffmpeg_path)` — concat WAVs with `ffmpeg -f concat`, then encode to 128k MP3 in one shot.
- `render.render_pages(pdf_path, output_dir, dpi=150)` — write `page_001.png` etc., record pixel dims back to manifest.
- Acceptance: mp3 plays end-to-end, page images render at expected DPI.

### M4 — Player v1 (text-only sync)

**Goal:** `player.html` loads `manifest.json` + `audiobook.mp3`, shows scrollable sentence list, highlights current sentence, auto-scrolls, lets user click a sentence to seek.

- No PDF page view yet.
- Bottom bar: play/pause, scrubber, time, current page indicator (text only).
- Keyboard: space, ←/→ (5s skip), j/k (prev/next sentence), `,` / `.` (slower/faster).
- Acceptance: works offline in Chrome and Firefox, no console errors.

### M5 — Player v2 (page + bbox highlight)

**Goal:** Two-pane layout. Left = current page image with translucent yellow rectangle on the active sentence's bbox. Right = sentence list (M4 behavior).

- Page swaps when the current sentence's `page` changes.
- Bbox → pixel conversion using `pages[i]` scale factors.
- Click on a region of the page → seek to nearest sentence whose bbox contains the click.
- Acceptance: highlight visually tracks the audio on the test book without drifting.

### M6 — CLI + packaging

**Goal:** `audiobook-ish build PDF --out DIR` does everything end-to-end. Sub-commands for individual stages (`extract`, `synthesize`, `combine`, `render`, `bundle-player`).

- `--voice`, `--speed`, `--dpi`, `--bitrate`, `--ffmpeg` flags.
- Progress bars (tqdm).
- Smart defaults; everything resumable.
- Acceptance: clean re-run after a half-finished run produces identical output.

### M7 — Polish

- Chapter detection (heading heuristic) → chapter nav in player.
- Bookmarks (localStorage in player).
- Variable-speed playback in player (separate from synthesis speed).
- Light/dark theme.
- Optional: word-level karaoke highlight (needs forced alignment — out of scope for v1).

## Open questions

- **Sentence boundaries across pages.** Some sentences span a page break. Easiest: assign to the page where they *start*, but visually highlight on the page currently visible. Defer to M5.
- **Per-sentence vs per-paragraph synthesis.** Per-sentence gives best sync resolution but more overhead. Per-paragraph is faster. **Decision: per-sentence for v1**; revisit if synthesis is too slow.
- **Output format.** MP3 keeps file sizes reasonable. Should we also offer M4A/Opus? Defer.
- **Multi-voice support.** Kokoro has multiple voices. Out of scope for v1 (single voice per book).
- **Mobile player.** Goal is browser-on-laptop for v1. Mobile-friendly CSS is nice-to-have but not required.

## Non-goals (for now)

- Live streaming / progressive playback while synthesizing
- EPUB / DOCX / TXT input (PDF only for v1)
- Cloud hosting, accounts, sync
- Word-level highlight (requires forced alignment)
- Voice cloning / custom voices

## Legacy reference

`legacy/generate_audiobook.py` is the original chunk-level prototype. It works (generates a single MP3) but has no sync. Useful for the text-cleaning ruleset and the Kokoro invocation pattern. **Do not import from it.** Reimplement cleanly in `audiobook_ish/`.
