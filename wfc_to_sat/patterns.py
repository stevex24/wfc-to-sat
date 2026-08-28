from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pattern:
    id: int
    rows: tuple
    frequency: int = 0


def pattern_key(rows: tuple) -> str:
    return "/".join(str(row) for row in rows)


def extract_patterns(text_grid: list[str], pattern_size: int, *, extraction="nonwrapped"):
    height = len(text_grid)
    width = len(text_grid[0])

    counts = Counter()

    _validate_extraction(extraction)
    y_range = range(height) if extraction == "periodic" else range(height - pattern_size + 1)
    x_range = range(width) if extraction == "periodic" else range(width - pattern_size + 1)
    for y in y_range:
        for x in x_range:
            rows = _window(text_grid, x, y, pattern_size, extraction)

            counts[rows] += 1

    patterns = []

    for i, (rows, frequency) in enumerate(counts.items()):
        patterns.append(
            Pattern(
                id=i,
                rows=rows,
                frequency=frequency
            )
        )

    return patterns


def extract_pattern_occurrence_grid(
    text_grid, pattern_size: int, patterns=None, *, extraction="nonwrapped"
):
    """Return unique patterns and the source grid of their occurrence IDs.

    The occurrence grid has one cell per valid top-left pattern position and
    uses the same explicit extraction policy as :func:`extract_patterns`.
    """
    if patterns is None:
        patterns = extract_patterns(text_grid, pattern_size, extraction=extraction)
    _validate_extraction(extraction)
    ids = {pattern.rows: pattern.id for pattern in patterns}
    height = len(text_grid)
    width = len(text_grid[0])
    occurrences = []
    y_range = range(height) if extraction == "periodic" else range(height - pattern_size + 1)
    x_range = range(width) if extraction == "periodic" else range(width - pattern_size + 1)
    for y in y_range:
        row = []
        for x in x_range:
            rows = _window(text_grid, x, y, pattern_size, extraction)
            row.append(ids[rows])
        occurrences.append(tuple(row))
    return patterns, tuple(occurrences)


def _hashable_slice(row, start, stop):
    """Preserve text rows and make other cell sequences hashable."""
    segment = row[start:stop]
    return segment if isinstance(segment, str) else tuple(segment)


def _window(grid, x, y, size, extraction):
    if extraction == "nonwrapped":
        return tuple(_hashable_slice(grid[y + dy], x, x + size) for dy in range(size))
    height, width = len(grid), len(grid[0])
    return tuple(
        tuple(grid[(y + dy) % height][(x + dx) % width] for dx in range(size))
        for dy in range(size)
    )


def _validate_extraction(extraction):
    if extraction not in {"nonwrapped", "periodic"}:
        raise ValueError("extraction must be 'nonwrapped' or 'periodic'")


def load_image_grid(image_path):
    """Load a PNG or JPEG as a rectangular grid of RGBA pixel tuples."""
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "Image extraction requires Pillow; install dependencies with "
            "'python3 -m pip install -r requirements.txt'"
        ) from error

    path = Path(image_path)
    with Image.open(path) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError(
                f"unsupported image format {image.format!r}; expected PNG or JPEG"
            )
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixel_access = rgba.load()
        pixels = [
            pixel_access[x, y]
            for y in range(height)
            for x in range(width)
        ]

    return [
        tuple(pixels[y * width : (y + 1) * width])
        for y in range(height)
    ]


def extract_patterns_from_image(image_path, pattern_size: int, *, extraction="nonwrapped"):
    """Extract patterns from the RGBA pixels of a PNG or JPEG image."""
    return extract_patterns(
        load_image_grid(image_path), pattern_size, extraction=extraction
    )
