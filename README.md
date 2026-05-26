# Audiobook-ish

> Speechify, but not really.

Turn any PDF into a **page-synced audiobook** you can listen to *and* read along with. Local, open-source, runs offline once models are cached.

- **Listen** — high-quality narration via [Kokoro TTS](https://github.com/hexgrad/kokoro) (default voice: `af_nicole` at 1.2x)
- **Follow along** — the current sentence is highlighted on the rendered PDF page and in a scrollable text pane
- **Jump anywhere** — click a sentence (or a region on the page) and the audio seeks there
- **Resumable** — per-sentence checkpointing; interrupt and restart any time

## Status

Core pipeline + synced player are implemented through M7. See [`PLAN.md`](./PLAN.md) for milestone details and [`legacy/`](./legacy) for the first chunk-level prototype.

## Quick start

```bash
pip install -e .
audiobook-ish build path/to/book.pdf --voice af_nicole --speed 1.2 --out examples/book
open examples/book/player.html
```

That produces:

```
examples/book/
├── audiobook.mp3        # full narration, ~128kbps
├── manifest.json        # sentence timing + page + bbox + chapters
├── manifest.js          # file:// bootstrap fallback for browser playback
├── pages/page_001.png   # rendered PDF pages
├── sentences/           # per-sentence wavs (kept for resume)
├── player.html          # standalone offline player
├── player.css
└── player.js
```

Open `player.html` in any browser. No server, no install, no telemetry.

## Why "but not really"?

Speechify is great. It's also a SaaS that uploads your books to someone else's cloud, charges a subscription, and locks you to their voices. This project does the same core thing — sync audio to text and pages — but:

- runs entirely on your machine
- uses [Kokoro](https://github.com/hexgrad/kokoro) (Apache-2.0, ~82M params, runs on CPU)
- outputs plain files you own forever
- is hackable Python in a couple hundred lines

## Architecture

```
PDF ─► extract ─► sentences (text + page + bbox)
                       │
                       ▼
                  synthesize ─► per-sentence WAVs + durations
                       │
                       ▼
                   manifest ─► manifest.json
                       │
                       ├──► combine ─► audiobook.mp3
                       └──► render  ─► pages/*.png
                                          │
                                          ▼
                                    player.html (HTML + JS, offline)
```

See [`PLAN.md`](./PLAN.md) for the full design and [`context.md`](./context.md) if you're an AI agent contributing.

## Requirements

- Python 3.10+
- `ffmpeg` on `PATH` (or set `AUDIOBOOK_ISH_FFMPEG=/path/to/ffmpeg`)
- ~1 GB free disk per ~10 hours of audio
- CPU is fine; GPU optional for faster synthesis

## License

MIT. Voice models distributed by Kokoro under Apache-2.0.
