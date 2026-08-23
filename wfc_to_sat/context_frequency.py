"""Context-frequency preprocessing shared by WFC decision heuristics.

The four-neighbor context order is north, east, south, west.  Source
boundaries and neighbors that are not yet decided are both represented by
the explicit :data:`UNK` marker, following Bateni, Karth, and Smith.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Generic, Hashable, Iterable, Sequence, TypeVar


Tile = TypeVar("Tile", bound=Hashable)
ContextValue = Hashable
Context = tuple[ContextValue, ContextValue, ContextValue, ContextValue]


class _Unknown(Enum):
    VALUE = "UNK"

    def __repr__(self) -> str:
        return "UNK"

    def __str__(self) -> str:
        return "UNK"


UNK = _Unknown.VALUE
"""Explicit marker for an out-of-bounds or not-yet-decided neighbor."""


@dataclass(frozen=True)
class WeightLookup(Generic[Tile]):
    """Candidate weights and whether ordinary-frequency fallback was used."""

    weights: tuple[int, ...]
    used_frequency_fallback: bool


class ContextFrequencies(Generic[Tile]):
    """Count source tiles and their complete and masked contexts."""

    def __init__(self, source_grid: Sequence[Sequence[Tile]]) -> None:
        rows = tuple(tuple(row) for row in source_grid)
        if not rows or not rows[0]:
            raise ValueError("source grid must be nonempty")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("source grid must be rectangular")
        if any(tile is UNK for row in rows for tile in row):
            raise ValueError("source tiles cannot use the reserved UNK marker")

        self.source_grid = rows
        self.width = width
        self.height = len(rows)
        self._tile_counts: Counter[Tile] = Counter()
        self._context_counts: Counter[tuple[Tile, Context]] = Counter()
        self._complete_contexts: list[tuple[Tile, Context]] = []

        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                context = self._context_at(x, y)
                self._tile_counts[tile] += 1
                self._complete_contexts.append((tile, context))
                for masked in masked_contexts(context):
                    self._context_counts[(tile, masked)] += 1

    @property
    def tiles(self) -> tuple[Tile, ...]:
        """Unique source tiles in deterministic first-occurrence order."""
        return tuple(self._tile_counts)

    @property
    def complete_contexts(self) -> tuple[tuple[Tile, Context], ...]:
        """One unmasked ``(tile, context)`` pair per source coordinate."""
        return tuple(self._complete_contexts)

    def tile_frequency(self, tile: Tile) -> int:
        return self._tile_counts[tile]

    def frequency(self, tile: Tile, context: Context) -> int:
        """Return ``freq(tile, context)``, or zero for an unseen pair."""
        _validate_context(context)
        return self._context_counts[(tile, context)]

    def context_was_seen(
        self,
        context: Context,
        candidates: Iterable[Tile] | None = None,
    ) -> bool:
        """Whether the context occurred for any requested source tile."""
        _validate_context(context)
        options = self.tiles if candidates is None else tuple(candidates)
        return any(self.frequency(tile, context) > 0 for tile in options)

    def candidate_weights(
        self,
        candidates: Iterable[Tile],
        context: Context,
    ) -> WeightLookup[Tile]:
        """Look up context weights, falling back only when all are zero."""
        _validate_context(context)
        options = tuple(candidates)
        for tile in options:
            if tile not in self._tile_counts:
                raise KeyError(f"candidate tile is absent from source: {tile!r}")
        weights = tuple(self.frequency(tile, context) for tile in options)
        if options and not any(weights):
            return WeightLookup(
                tuple(self.tile_frequency(tile) for tile in options),
                used_frequency_fallback=True,
            )
        return WeightLookup(weights, used_frequency_fallback=False)

    def _context_at(self, x: int, y: int) -> Context:
        def value(nx: int, ny: int) -> ContextValue:
            if 0 <= nx < self.width and 0 <= ny < self.height:
                return self.source_grid[ny][nx]
            return UNK

        return (
            value(x, y - 1),
            value(x + 1, y),
            value(x, y + 1),
            value(x - 1, y),
        )


def masked_contexts(context: Context) -> tuple[Context, ...]:
    """Return each unique context formed by masking known values with UNK."""
    _validate_context(context)
    choices = tuple((UNK,) if value is UNK else (value, UNK) for value in context)
    return tuple(product(*choices))  # type: ignore[return-value]


def _validate_context(context: Context) -> None:
    if len(context) != 4:
        raise ValueError("a 2D four-neighbor context must contain four values")
