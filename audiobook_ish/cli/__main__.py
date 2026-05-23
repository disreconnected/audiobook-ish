"""Command-line entry point.

Usage (target):
    audiobook-ish build PDF --out DIR [--voice af_nicole] [--speed 1.2] [--dpi 150]
    audiobook-ish extract PDF --out manifest.json
    audiobook-ish synthesize manifest.json --out DIR
    audiobook-ish combine DIR --out audiobook.mp3
    audiobook-ish render PDF --out DIR/pages
    audiobook-ish bundle-player DIR

See PLAN.md M6.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audiobook-ish",
        description="Generate page-synced audiobooks from PDFs using Kokoro TTS.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Run the full pipeline end-to-end")
    build.add_argument("pdf")
    build.add_argument("--out", required=True)
    build.add_argument("--voice", default="af_nicole")
    build.add_argument("--speed", type=float, default=1.2)
    build.add_argument("--dpi", type=int, default=150)
    build.add_argument("--bitrate", default="128k")

    args = parser.parse_args(argv)

    if args.cmd == "build":
        print("audiobook-ish: CLI scaffolded; pipeline not implemented yet.")
        print("See PLAN.md for the milestone roadmap.")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
