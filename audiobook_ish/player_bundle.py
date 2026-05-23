"""Copy static player assets into an output directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import AudiobookIshError


def bundle_player(output_dir: Path, player_source_dir: Path | None = None) -> None:
    """Copy player HTML/CSS/JS (+ assets dir) into ``output_dir``.

    Layout produced:

        output_dir/
        ├── player.html
        ├── player.css
        ├── player.js
        └── assets/
    """
    output_dir = Path(output_dir)
    src = (
        Path(player_source_dir)
        if player_source_dir is not None
        else Path(__file__).resolve().parents[1] / "player"
    )
    if not src.is_dir():
        raise AudiobookIshError(f"Player source directory not found: {src}")

    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = {
        "index.html": "player.html",
        "player.css": "player.css",
        "player.js": "player.js",
    }
    for src_name, dst_name in mapping.items():
        src_path = src / src_name
        if not src_path.is_file():
            raise AudiobookIshError(f"Missing player asset: {src_path}")
        shutil.copy2(src_path, output_dir / dst_name)

    assets_src = src / "assets"
    assets_dst = output_dir / "assets"
    if assets_src.exists():
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
