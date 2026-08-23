"""Independent oracle for pattern extraction and overlap compatibility.

The reference extractor reads every cell by coordinate instead of using the
production extractor's row slicing. Overlaps are checked by placing patterns
on a shared coordinate canvas instead of comparing row slices.
"""

from collections import Counter
from dataclasses import dataclass

from wfc_to_sat.compatibility import (
    build_compatibility,
    overlaps_down,
    overlaps_right,
)
from wfc_to_sat.patterns import extract_patterns


@dataclass(frozen=True)
class PatternValidationReport:
    """Counts and results for one exhaustive extraction/overlap comparison."""

    windows: int
    unique_patterns: int
    duplicate_occurrences: int
    right_pairs: int
    down_pairs: int
    extraction_identical: bool
    overlaps_identical: bool


def independently_count_windows(text_grid, pattern_size):
    """Count square windows by reading each source coordinate individually."""
    if pattern_size <= 0:
        raise ValueError("pattern size must be positive")
    if not text_grid or not text_grid[0]:
        raise ValueError("text grid must be nonempty")
    width = len(text_grid[0])
    if any(len(row) != width for row in text_grid):
        raise ValueError("text grid must be rectangular")

    counts = Counter()
    for origin_y in range(len(text_grid) - pattern_size + 1):
        for origin_x in range(width - pattern_size + 1):
            rows = []
            for pattern_y in range(pattern_size):
                cells = []
                for pattern_x in range(pattern_size):
                    cells.append(
                        text_grid[origin_y + pattern_y][origin_x + pattern_x]
                    )
                rows.append(
                    "".join(cells)
                    if isinstance(text_grid[origin_y + pattern_y], str)
                    else tuple(cells)
                )
            counts[tuple(rows)] += 1
    return counts


def independently_pattern_id_grid(text_grid, pattern_size, patterns):
    """Map every source-window position to an extracted ID by oracle rows."""
    pattern_ids = {pattern.rows: pattern.id for pattern in patterns}
    if len(pattern_ids) != len(patterns):
        raise AssertionError("identical patterns do not have one unique ID")

    height = len(text_grid) - pattern_size + 1
    width = len(text_grid[0]) - pattern_size + 1
    id_grid = []
    observed_ids = Counter()
    observed_rows_by_id = {}
    for origin_y in range(height):
        row_ids = []
        for origin_x in range(width):
            rows = []
            for pattern_y in range(pattern_size):
                cells = tuple(
                    text_grid[origin_y + pattern_y][origin_x + pattern_x]
                    for pattern_x in range(pattern_size)
                )
                source_row = text_grid[origin_y + pattern_y]
                rows.append("".join(cells) if isinstance(source_row, str) else cells)
            window = tuple(rows)
            pattern_id = pattern_ids[window]
            previous = observed_rows_by_id.setdefault(pattern_id, window)
            if previous != window:
                raise AssertionError(f"pattern ID {pattern_id} maps to multiple windows")
            row_ids.append(pattern_id)
            observed_ids[pattern_id] += 1
        id_grid.append(tuple(row_ids))

    expected_frequencies = {pattern.id: pattern.frequency for pattern in patterns}
    if dict(observed_ids) != expected_frequencies:
        raise AssertionError(
            f"heat-map frequencies mismatch: expected {expected_frequencies}, "
            f"got {dict(observed_ids)}"
        )
    if sum(observed_ids.values()) != width * height:
        raise AssertionError("heat-map frequencies do not sum to extracted windows")
    return tuple(id_grid)


def independently_overlap(first, second, offset_x, offset_y):
    """Place two patterns on a shared canvas and reject conflicting cells."""
    canvas = {}
    for pattern, origin_x, origin_y in (
        (first, 0, 0),
        (second, offset_x, offset_y),
    ):
        for y, row in enumerate(pattern.rows):
            for x, value in enumerate(row):
                coordinate = (origin_x + x, origin_y + y)
                previous = canvas.get(coordinate)
                if previous is not None and previous != value:
                    return False
                canvas[coordinate] = value
    return True


def validate_patterns_and_overlaps(text_grid, pattern_size):
    """Compare production extraction and compatibility with both oracles."""
    expected_counts = independently_count_windows(text_grid, pattern_size)
    patterns = extract_patterns(text_grid, pattern_size)
    extracted_rows = [pattern.rows for pattern in patterns]
    if len(extracted_rows) != len(set(extracted_rows)):
        raise AssertionError(f"duplicate extracted patterns: {extracted_rows}")
    actual_counts = Counter(
        {pattern.rows: pattern.frequency for pattern in patterns}
    )

    ids = [pattern.id for pattern in patterns]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"duplicate pattern IDs: {ids}")
    if any(pattern.frequency <= 0 for pattern in patterns):
        raise AssertionError("every extracted pattern must have positive frequency")

    extraction_identical = actual_counts == expected_counts
    if not extraction_identical:
        raise AssertionError(
            f"extraction mismatch: expected {expected_counts}, got {actual_counts}"
        )

    allowed = build_compatibility(patterns)
    expected_directions = {"right", "down"}
    if set(allowed) != expected_directions:
        raise AssertionError(f"unexpected compatibility directions: {set(allowed)}")

    expected = {"right": {}, "down": {}}
    for first in patterns:
        expected["right"][first.id] = set()
        expected["down"][first.id] = set()
        for second in patterns:
            right = independently_overlap(first, second, 1, 0)
            down = independently_overlap(first, second, 0, 1)

            if overlaps_right(first, second) != right:
                raise AssertionError(
                    f"right-overlap mismatch for {first.id} -> {second.id}"
                )
            if overlaps_down(first, second) != down:
                raise AssertionError(
                    f"down-overlap mismatch for {first.id} -> {second.id}"
                )
            if right:
                expected["right"][first.id].add(second.id)
            if down:
                expected["down"][first.id].add(second.id)

    for direction in expected_directions:
        if set(allowed[direction]) != set(ids):
            raise AssertionError(
                f"{direction} compatibility has incorrect source pattern IDs"
            )
        for pattern_id in ids:
            neighbors = allowed[direction][pattern_id]
            if len(neighbors) != len(set(neighbors)):
                raise AssertionError(
                    f"duplicate {direction} overlaps for pattern {pattern_id}: "
                    f"{neighbors}"
                )
            if set(neighbors) != expected[direction][pattern_id]:
                raise AssertionError(
                    f"{direction} compatibility mismatch for pattern {pattern_id}: "
                    f"expected {expected[direction][pattern_id]}, got {neighbors}"
                )

    windows = sum(expected_counts.values())
    return PatternValidationReport(
        windows=windows,
        unique_patterns=len(expected_counts),
        duplicate_occurrences=windows - len(expected_counts),
        right_pairs=sum(len(neighbors) for neighbors in expected["right"].values()),
        down_pairs=sum(len(neighbors) for neighbors in expected["down"].values()),
        extraction_identical=True,
        overlaps_identical=True,
    )
