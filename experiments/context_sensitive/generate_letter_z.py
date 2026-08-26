#!/usr/bin/env python3
"""Reproducibly generate the exact 16x16 binary letter-Z benchmark."""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "examples" / "letter-z.png"


def letter_z_pixels(size: int = 16):
    if size != 16:
        raise ValueError("the benchmark is defined only at 16x16")
    return tuple(
        tuple((0, 0, 0, 255) if y in (0, 15) or x + y == 15 else (255, 255, 255, 255)
              for x in range(16))
        for y in range(16)
    )


def write_letter_z(path: Path = OUTPUT) -> Path:
    pixels = letter_z_pixels()
    image = Image.new("RGBA", (16, 16))
    image.putdata([pixel for row in pixels for pixel in row])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


if __name__ == "__main__":
    print(write_letter_z())
