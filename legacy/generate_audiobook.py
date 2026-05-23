"""Generate audiobook from Crime and Punishment PDF using Kokoro TTS."""

import json
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np
import pymupdf as fitz
import soundfile as sf
from kokoro import KPipeline

PDF_PATH = Path(r"C:\Users\Computer\Downloads\Documents\crime-and-punishment.pdf")
OUTPUT_MP3 = Path(r"C:\Users\Computer\Documents\Audiobook-ish\crime-and-punishment-audiobook.mp3")
OUTPUT_WAV = OUTPUT_MP3.with_suffix(".wav")
CLEANED_TEXT = Path(r"C:\Users\Computer\Documents\Audiobook-ish\crime-and-punishment-cleaned.txt")
CHUNKS_DIR = Path(r"C:\Users\Computer\Documents\Audiobook-ish\chunks")
PROGRESS_FILE = CHUNKS_DIR / "progress.json"
FFMPEG = Path(
    r"C:\Users\Computer\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
)

VOICE = "af_nicole"
SPEED = 1.2
SAMPLE_RATE = 24000
CHUNK_SIZE = 5000

SKIP_LINE_PATTERNS = [
    re.compile(r"^Download free eBooks of classic literature", re.I),
    re.compile(r"^novels at Planet eBook\.", re.I),
    re.compile(r"^Subscribe to our free eBooks blog", re.I),
    re.compile(r"^and email newsletter\.", re.I),
    re.compile(r"^Free eBooks at Planet eBook\.com$", re.I),
    re.compile(r"^Crime and Punishment$"),
    re.compile(r"^By Fyodor Dostoevsky$"),
    re.compile(r"^\d+$"),
    re.compile(r"^[\uf600-\uf6ff]+$"),
]


def clean_text(raw: str) -> str:
    """Normalize PDF text for TTS: ASCII novel punctuation only."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Rejoin words split across line breaks with hyphens.
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

    # Drop boilerplate lines and page markers.
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in SKIP_LINE_PATTERNS):
            continue
        lines.append(stripped)
    text = " ".join(lines)

    # Map typographic punctuation to spoken-friendly ASCII forms.
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": " -- ",
        "\u2013": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\ufb01": "fi",
        "\ufb02": "fl",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove private-use / control characters from PDF extraction.
    text = re.sub(r"[\uf600-\uf6ff\u0000-\u001f\u007f-\u009f]", "", text)

    # Transliterate accented letters to ASCII (naive, fiancee, etc.).
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Keep only characters that belong in spoken novel text.
    text = re.sub(r"[^A-Za-z0-9 .,!?;:'\"()\-\[\]\n]", " ", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def split_into_chunks(text: str, max_len: int = CHUNK_SIZE) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        extra = len(sentence) + (1 if current else 0)
        if length + extra <= max_len:
            current.append(sentence)
            length += extra
        else:
            if current:
                chunks.append(" ".join(current))
            if len(sentence) > max_len:
                for i in range(0, len(sentence), max_len):
                    chunks.append(sentence[i : i + max_len])
                current = []
                length = 0
            else:
                current = [sentence]
                length = len(sentence)

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_wav_path(index: int) -> Path:
    return CHUNKS_DIR / f"chunk_{index:04d}.wav"


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"completed": [], "total": 0}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def generate_chunk_audio(pipeline: KPipeline, chunk: str, index: int) -> None:
    wav_path = chunk_wav_path(index)
    if wav_path.exists():
        return

    parts = [audio for _, _, audio in pipeline(chunk, voice=VOICE, speed=SPEED)]
    if not parts:
        raise RuntimeError(f"No audio generated for chunk {index}")

    audio = np.concatenate(parts)
    sf.write(wav_path, audio, SAMPLE_RATE)
    print(f"  Chunk {index + 1}: {len(chunk)} chars -> {len(audio) / SAMPLE_RATE:.1f}s", flush=True)


def combine_chunks(num_chunks: int) -> np.ndarray:
    segments = []
    for i in range(num_chunks):
        path = chunk_wav_path(i)
        if not path.exists():
            raise FileNotFoundError(f"Missing chunk audio: {path}")
        data, sr = sf.read(path)
        if sr != SAMPLE_RATE:
            raise ValueError(f"Unexpected sample rate in {path}: {sr}")
        segments.append(data)
    return np.concatenate(segments)


def convert_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    cmd = [
        str(FFMPEG),
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(mp3_path),
        "-y",
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def verify_clean_text(text: str) -> None:
    bad = sorted({c for c in text if ord(c) > 127})
    if bad:
        raise ValueError(f"Non-ASCII characters remain after cleaning: {bad[:20]}")


def main() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    print("Extracting text from PDF...", flush=True)
    raw_text = extract_text_from_pdf(PDF_PATH)
    print(f"  Raw text: {len(raw_text):,} characters", flush=True)

    print("Cleaning text...", flush=True)
    text = clean_text(raw_text)
    verify_clean_text(text)
    CLEANED_TEXT.write_text(text, encoding="utf-8")
    print(f"  Cleaned text: {len(text):,} characters -> {CLEANED_TEXT}", flush=True)

    chunks = split_into_chunks(text)
    print(f"  Split into {len(chunks)} chunks (~{CHUNK_SIZE} chars each)", flush=True)

    progress = load_progress()
    progress["total"] = len(chunks)
    save_progress(progress)

    print("Initializing Kokoro TTS (af_nicole @ 1.2x)...", flush=True)
    pipeline = KPipeline(lang_code="a")

    for i, chunk in enumerate(chunks):
        generate_chunk_audio(pipeline, chunk, i)
        if i not in progress["completed"]:
            progress["completed"].append(i)
            save_progress(progress)
        if (i + 1) % 10 == 0 or i == len(chunks) - 1:
            print(f"  Progress: {i + 1}/{len(chunks)} chunks", flush=True)

    print("Combining audio chunks...", flush=True)
    final_audio = combine_chunks(len(chunks))
    duration_sec = len(final_audio) / SAMPLE_RATE
    sf.write(OUTPUT_WAV, final_audio, SAMPLE_RATE)
    print(f"  WAV saved: {OUTPUT_WAV} ({duration_sec / 60:.1f} min)", flush=True)

    print("Converting to MP3...", flush=True)
    convert_to_mp3(OUTPUT_WAV, OUTPUT_MP3)

    hours = int(duration_sec // 3600)
    minutes = int((duration_sec % 3600) // 60)
    seconds = int(duration_sec % 60)
    print("\n=== COMPLETE ===", flush=True)
    print(f"Output: {OUTPUT_MP3}", flush=True)
    print(f"Duration: {hours}h {minutes}m {seconds}s ({duration_sec:.1f} seconds)", flush=True)


if __name__ == "__main__":
    main()
