"""Ordered, axis-specific lag-r pair-frequency measurements."""

from __future__ import annotations

from collections import Counter

from experiments.context_sensitive.core_experiment import kl_target_source


def _shape(grid):
    if not grid or not grid[0]:
        raise ValueError("grid must be non-empty")
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        raise ValueError("grid must be rectangular")
    return width, len(grid)


def lag_pair_counts(grid, lag, axis):
    """Count ordered pairs separated by ``lag`` along one axis."""
    width, height = _shape(grid)
    if not isinstance(lag, int) or isinstance(lag, bool) or lag <= 0:
        raise ValueError("lag must be a positive integer")
    if axis not in ("horizontal", "vertical"):
        raise ValueError("axis must be 'horizontal' or 'vertical'")
    limit = width if axis == "horizontal" else height
    if lag >= limit:
        raise ValueError(f"lag {lag} is not available for {axis} dimension {limit}")
    counts = Counter()
    if axis == "horizontal":
        for row in grid:
            counts.update((row[x], row[x + lag]) for x in range(width - lag))
    else:
        for y in range(height - lag):
            counts.update((grid[y][x], grid[y + lag][x]) for x in range(width))
    return counts


def normalized(counts):
    total = sum(counts.values())
    if not total:
        raise ValueError("cannot normalize empty counts")
    return {key: value / total for key, value in counts.items()}


def aggregate_lag_counts(grids, lag, axis):
    """Deterministically pool raw counts before normalization."""
    result = Counter()
    for grid in grids:
        result.update(lag_pair_counts(grid, lag, axis))
    return result


def lag_kl(target_grids, source_grid, lag, axis):
    target = normalized(aggregate_lag_counts(target_grids, lag, axis))
    source = normalized(lag_pair_counts(source_grid, lag, axis))
    return kl_target_source(target, source)
