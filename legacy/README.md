# legacy/

The original chunk-level prototype that produced a single MP3 with no sync.

Keep this folder as **read-only reference** — useful for:

- the working text-cleaning ruleset (`generate_audiobook.py::clean_text`)
- the Kokoro `KPipeline` invocation pattern
- the chunked WAV outputs in `chunks/` if you want to compare audio quality with the new pipeline

Do not import from this folder into `audiobook_ish/`. Reimplement cleanly.
