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

### M1 — Sentence extraction with page tracking *(done)*

**Goal:** `extract.extract_sentences(pdf_path) -> list[Sentence]` works on a small fixture PDF and the real Crime & Punishment PDF.

- ✅ `PyMuPDF`'s `page.get_text("dict")` for per-line text + bboxes.
- ✅ Hyphenated line breaks rejoined (both cross-line and in-line `word- word` artifacts).
- ✅ Boilerplate stripping: empty lines, pure-digit page numbers, PUA glyphs, Planet eBook headers.
- ✅ `clean_for_tts` ruleset: smart quotes / em dash / ellipsis / accents / ligatures / zero-width / PUA / collapse whitespace → ASCII-only.
- ✅ Sentence split on `(?<=[.!?])\s+`; each sentence anchored to its *last* overlapping line's page, bbox = union of overlapping lines on that page.
- ✅ 33 unit tests + 1 opt-in integration test (set `AUDIOBOOK_ISH_TEST_PDF`).
- **Validated on Crime and Punishment:** 13,239 sentences, 0 non-ASCII chars, pages monotonically non-decreasing across the book, all bboxes well-formed. Median sentence length 66 chars.

### M2 — Per-sentence synthesis with manifest *(done)*

**Goal:** `synthesize.synthesize(sentences, output_dir, voice, speed) -> list[Sentence]` produces `sentences/sent_NNNNN.wav` per sentence and fills in `start_sec` / `end_sec`.

- ✅ One `KPipeline` instance, lazily constructed (no model load if all WAVs are already on disk).
- ✅ If a sentence's WAV exists, its duration is read from disk and Kokoro is not invoked.
- ✅ Multi-segment outputs from Kokoro are concatenated before write.
- ✅ Cumulative `start_sec` / `end_sec` filled in place on the Sentence list.
- ✅ `on_progress(idx, sentence)` callback for the CLI to write partial manifest checkpoints.
- ✅ Pipeline is injectable (`PipelineLike` Protocol) so tests use a `FakePipeline` — no real model load required for unit tests.
- ✅ 8 unit tests + 1 opt-in real-Kokoro integration test.
- **Validated end-to-end:** resume across two invocations on the real PDF — second run skipped the 2 already-synthesized sentences (0 Kokoro calls) and continued with cumulative timing intact. ~7.5s synthesis per sentence on CPU, matching the earlier 2.3-2.5x realtime measurement.

### M3 — Combine + render *(done)*

**Goal:** Produce `audiobook.mp3` and `pages/page_NNN.png`.

- ✅ `combine.combine(sentences_dir, output_mp3, bitrate)` uses `ffmpeg -f concat -safe 0 -i list.txt -c:a libmp3lame -b:a 128k`. Concat-list paths use forward slashes so they parse cleanly inside single-quoted directives on Windows.
- ✅ Gap detection: missing sentence ids in the WAV directory raise `AudiobookIshError` with a sample of the missing ids.
- ✅ `render.render_pages(pdf_path, output_dir, dpi=150)` writes `pages/page_NNN.png` (auto-padded to 4 digits for >999-page books) and returns a `list[PageInfo]` with pixel + PDF-point dims.
- ✅ Both are resumable: existing PNGs are kept (pixel dims read via `pymupdf.Pixmap`); `combine` is one-shot so resuming means "no-op if MP3 exists" via caller logic.
- ✅ 17 new tests (8 render, 9 combine, real-ffmpeg integration tests skipped automatically when ffmpeg is absent).
- **Validated on Crime and Punishment:** 5 pages rendered at 150 DPI in 0.15s (672x1008 px, ~200 KB avg), 2-sentence MP3 produced in 0.15s (224 KB for 14.2s of audio at 128kbps).

### M4 — Player v1 (text-only sync) *(done)*

**Goal:** `player.html` loads `manifest.json` + `audiobook.mp3`, shows scrollable sentence list, highlights current sentence, auto-scrolls, lets user click a sentence to seek.

- ✅ Text-only layout (page panel removed for this milestone).
- ✅ Bottom bar: play/pause, scrubber, time, current page indicator.
- ✅ Keyboard: space, ←/→ (5s skip), j/k (prev/next sentence), `,` / `.` (slower/faster).
- ✅ Binary-search sentence sync for efficient long-book playback.
- ✅ `manifest.js` fallback (`window.AUDIOBOOK_ISH_MANIFEST`) so playback works from `file://` without fetch/CORS issues; still supports `manifest.json` fetch when served over HTTP.
- ✅ Added `bundle_player(output_dir)` helper and `audiobook-ish bundle-player <out>` CLI command to copy `player.html`, `player.css`, `player.js`, and `assets/` into generated output folders.
- ✅ Smoke-tested end-to-end on a real PDF subset: generated MP3 + manifest + bundled player files in `examples/m4_smoke`.

### M5 — Player v2 (page + bbox highlight) *(done)*

**Goal:** Two-pane layout. Left = current page image with translucent yellow rectangle on the active sentence's bbox. Right = sentence list (M4 behavior).

- ✅ Two-pane layout restored. Left: rendered page image, right: sentence list.
- ✅ Active sentence drives page swap + translucent bbox highlight overlay.
- ✅ Bbox→pixel mapping uses `page.pdf_width_pt/pdf_height_pt` and rendered image client size.
- ✅ Clicking the page seeks audio to the matching sentence:
  - first tries bbox containment,
  - falls back to nearest bbox center on that page.
- ✅ Graceful fallback to text-only mode when `manifest.pages` is missing or page images fail to load.
- ✅ End-to-end smoke run on real PDF subset: generated `pages/page_001.png..page_767.png`, MP3, manifest files, and bundled player with no JS syntax errors (`node --check`).

### M6 — CLI + packaging *(done)*

**Goal:** `audiobook-ish build PDF --out DIR` does everything end-to-end. Sub-commands for individual stages (`extract`, `synthesize`, `combine`, `render`, `bundle-player`).

- ✅ `audiobook-ish build PDF --out DIR` now runs end-to-end:
  1) extract sentences, 2) synthesize sentence WAVs, 3) render pages,
  4) combine MP3, 5) write manifest.json + manifest.js + bundle player.
- ✅ Stage subcommands implemented:
  - `extract PDF --out sentences.json`
  - `synthesize sentences.json --out DIR`
  - `render PDF --out DIR`
  - `combine DIR --out audiobook.mp3`
  - `bundle-player DIR`
- ✅ Flags in place: `--voice`, `--speed`, `--sample-rate`, `--dpi`, `--bitrate`, `--ffmpeg`.
- ✅ Resumable checkpoints during synthesis via `--checkpoint-every` (writes partial manifest files so the player can open mid-run).
- ✅ Dev/test limiter `--max-sentences` for fast smoke validation.
- ⚠️ Progress bars (`tqdm`) deferred; currently stage markers are printed (`[1/5] ...`).
- **Acceptance validated:** full CLI smoke build on Crime and Punishment with `--max-sentences 8` completed successfully and produced a playable output folder with all expected artifacts.

### M7 — Polish *(done)*

- ✅ Chapter detection heuristic (`PART/BOOK/CHAPTER`) added from sentence stream and stored in manifest.
- ✅ Chapter jump selector added to player top bar (navigates by sentence anchor/time).
- ✅ Bookmarks added in player (localStorage persisted per source PDF).
- ✅ Variable-speed playback controls retained and expanded (`select` + keyboard `,` / `.` nudges).
- ✅ Light/dark theme toggle added (localStorage persisted per source PDF).
- ✅ Chapter detector hardened: case-sensitive keyword match (no false positives from prose), Roman-numeral case preserved, and PART/BOOK context disambiguates same-numbered chapters across parts.
- ❌ Word-level karaoke highlight still out of scope for v1 (requires forced alignment).

### M8 — Distribution packaging *(done)*

**Goal:** Make a finished build trivial to sideload onto a phone or share with a friend, without requiring a Python install on the consumer side.

- ✅ `package-m4b OUTPUT_DIR --to BOOK.m4b` re-encodes `audiobook.mp3` to AAC and embeds chapter markers from `manifest.chapters` via an ffmpeg ffmetadata file (`-map_chapters 1 -movflags +faststart`). Apple Books, VLC, and Smart AudioBook Player pick up the chapters natively.
- ✅ `package-zip OUTPUT_DIR --to BOOK.zip` archives the synced player (`player.html/.css/.js`, `manifest.json/.js`, `audiobook.mp3`, `pages/`, `assets/`) into a self-contained folder. `sentences/` and `sentences.json` are excluded — they exist only for resumable synthesis.
- ✅ Tests: 15 packaging tests cover ffmetadata content (timebase, chapter order, intro insertion, default titles), CLI flag wiring, the zip layout, the page-skip toggle, and error paths.
- **Acceptance validated:** packaged the full Crime and Punishment build → `crime-and-punishment.m4b` (757 MB, 41 chapters incl. intro + epilogue) and `crime-and-punishment-web.zip` (1.5 GB, 773 entries, all 767 page PNGs).

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
