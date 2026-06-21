from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    id: int
    rows: tuple[str, ...]
    frequency: int = 0


def pattern_key(rows: tuple[str, ...]) -> str:
    return "/".join(rows)


def extract_patterns(text_grid: list[str], pattern_size: int):
    height = len(text_grid)
    width = len(text_grid[0])

    counts = Counter()

    for y in range(height - pattern_size + 1):
        for x in range(width - pattern_size + 1):

            rows = tuple(
                text_grid[y + dy][x : x + pattern_size]
                for dy in range(pattern_size)
            )

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
