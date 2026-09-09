#!/usr/bin/env python3
"""Fetch the CC0 Kenney Tiny Town tiles referenced by the manifest."""

from __future__ import annotations

import io
import json
from pathlib import Path
import urllib.request
import zipfile


HERE = Path(__file__).resolve().parent


def ensure_assets(destination: Path | None = None) -> Path:
    destination = destination or HERE / "assets"
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    wanted = sorted({tile for values in manifest["tiles"].values() for tile in values})
    if all((destination / f"tile_{tile:04d}.png").is_file() for tile in wanted):
        return destination
    destination.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(manifest["asset_archive"], timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    for tile in wanted:
        name = f"Tiles/tile_{tile:04d}.png"
        (destination / Path(name).name).write_bytes(archive.read(name))
    return destination


if __name__ == "__main__":
    print(ensure_assets())
