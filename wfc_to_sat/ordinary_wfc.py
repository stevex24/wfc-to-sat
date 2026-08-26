"""Standalone ordinary WaveFunctionCollapse with no SAT/CDCL dependency.

The engine uses the standard WFC observe-then-propagate loop.  Selection and
decision are separate policies; milestone 02 implements lexical selection and
uniform, source-frequency, and context-frequency decisions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random
from typing import Generic, Hashable, Mapping, Sequence, TypeVar

from wfc_to_sat.context_frequency import Context, ContextFrequencies, MOORE, UNK, VON_NEUMANN


Tile = TypeVar("Tile", bound=Hashable)
Direction = str
DIRECTIONS: tuple[tuple[Direction, int, int], ...] = (
    ("north", 0, -1),
    ("east", 1, 0),
    ("south", 0, 1),
    ("west", -1, 0),
)


@dataclass(frozen=True)
class DecisionWeights(Generic[Tile]):
    candidates: tuple[Tile, ...]
    weights: tuple[int, ...]
    used_frequency_fallback: bool = False


@dataclass(frozen=True)
class WFCResult(Generic[Tile]):
    success: bool
    output: tuple[tuple[Tile | None, ...], ...]
    final_domains: tuple[tuple[tuple[Tile, ...], ...], ...]
    seed: int
    width: int
    height: int
    selection: str
    decision: str
    contradiction_policy: str
    attempts: int
    restarts: int
    contradictions: int
    observations: int
    context_lookups: int = 0
    context_fallbacks: int = 0


@dataclass(frozen=True)
class WFCModel(Generic[Tile]):
    """Immutable source statistics and directional adjacency rules."""

    tiles: tuple[Tile, ...]
    frequencies: Mapping[Tile, int]
    adjacency: Mapping[Direction, Mapping[Tile, tuple[Tile, ...]]]
    context_frequencies: ContextFrequencies[Tile] | None = None
    moore_context_frequencies: ContextFrequencies[Tile] | None = None

    @classmethod
    def from_tile_grid(cls, source_grid: Sequence[Sequence[Tile]]) -> "WFCModel[Tile]":
        contexts = ContextFrequencies(source_grid)
        moore_contexts = ContextFrequencies(source_grid, "moore")
        rows = contexts.source_grid
        tiles = contexts.tiles
        allowed: dict[Direction, dict[Tile, set[Tile]]] = {
            direction: {tile: set() for tile in tiles}
            for direction, _, _ in DIRECTIONS
        }
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                for direction, dx, dy in DIRECTIONS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < contexts.width and 0 <= ny < contexts.height:
                        allowed[direction][tile].add(rows[ny][nx])
        adjacency = {
            direction: {
                tile: tuple(option for option in tiles if option in table[tile])
                for tile in tiles
            }
            for direction, table in allowed.items()
        }
        return cls(
            tiles=tiles,
            frequencies={tile: contexts.tile_frequency(tile) for tile in tiles},
            adjacency=adjacency,
            context_frequencies=contexts,
            moore_context_frequencies=moore_contexts,
        )

    @classmethod
    def from_patterns(
        cls,
        patterns: Sequence[object],
        compatibility: Mapping[str, Mapping[int, Sequence[int]]],
        source_pattern_grid: Sequence[Sequence[int]] | None = None,
    ) -> "WFCModel[int]":
        """Adapt repository pattern IDs and right/down overlap compatibility."""
        pattern_ids = tuple(int(getattr(pattern, "id")) for pattern in patterns)
        frequencies = {
            int(getattr(pattern, "id")): int(getattr(pattern, "frequency"))
            for pattern in patterns
        }
        east = {
            pattern_id: tuple(int(item) for item in compatibility["right"][pattern_id])
            for pattern_id in pattern_ids
        }
        south = {
            pattern_id: tuple(int(item) for item in compatibility["down"][pattern_id])
            for pattern_id in pattern_ids
        }
        west = _inverse_adjacency(pattern_ids, east)
        north = _inverse_adjacency(pattern_ids, south)
        contexts = (
            ContextFrequencies(source_pattern_grid)
            if source_pattern_grid is not None
            else None
        )
        moore_contexts = (
            ContextFrequencies(source_pattern_grid, "moore")
            if source_pattern_grid is not None
            else None
        )
        return WFCModel(
            tiles=pattern_ids,
            frequencies=frequencies,
            adjacency={"north": north, "east": east, "south": south, "west": west},
            context_frequencies=contexts,
            moore_context_frequencies=moore_contexts,
        )

    def validate(self) -> None:
        if not self.tiles or len(self.tiles) != len(set(self.tiles)):
            raise ValueError("model tiles must be nonempty and unique")
        tile_set = set(self.tiles)
        if set(self.frequencies) != tile_set:
            raise ValueError("model frequencies must define every tile")
        if any(self.frequencies[tile] <= 0 for tile in self.tiles):
            raise ValueError("model frequencies must be positive")
        if set(self.adjacency) != {item[0] for item in DIRECTIONS}:
            raise ValueError("model must define all four adjacency directions")
        for direction, table in self.adjacency.items():
            if set(table) != tile_set:
                raise ValueError(f"{direction} adjacency must define every tile")
            if any(not set(options) <= tile_set for options in table.values()):
                raise ValueError(f"{direction} adjacency references an unknown tile")


class OrdinaryWFC(Generic[Tile]):
    """Mutable wave state for one deterministic-seed ordinary-WFC run.

    A neighbor is known to the context heuristic whenever its current domain
    is singleton, including when propagation—not explicit observation—created
    that singleton.  This matches the paper authors' reference implementation.
    """

    def __init__(
        self,
        model: WFCModel[Tile],
        width: int,
        height: int,
        *,
        selection: str = "lexical",
        decision: str = "frequency",
        seed: int = 0,
    ) -> None:
        model.validate()
        if width <= 0 or height <= 0:
            raise ValueError("output dimensions must be positive")
        if selection != "lexical":
            raise ValueError(f"unsupported selection heuristic: {selection!r}")
        if decision not in {"uniform", "frequency", "context", "context_moore"}:
            raise ValueError(f"unsupported decision heuristic: {decision!r}")
        if decision == "context" and model.context_frequencies is None:
            raise ValueError("context decision requires source context frequencies")
        if decision == "context_moore" and model.moore_context_frequencies is None:
            raise ValueError("Moore context decision requires source context frequencies")

        self.model = model
        self.width = width
        self.height = height
        self.selection = selection
        self.decision = decision
        self.seed = seed
        self.random = random.Random(seed)
        self._tile_index = {tile: index for index, tile in enumerate(model.tiles)}
        self._full_domain = (1 << len(model.tiles)) - 1
        self._domains = [self._full_domain] * (width * height)
        self.observed: set[tuple[int, int]] = set()
        self.contradictions = 0
        self.context_lookups = 0
        self.context_fallbacks = 0

    def domain_at(self, x: int, y: int) -> tuple[Tile, ...]:
        return self._domain_values(self._domains[self._cell(x, y)])

    def select_location(self) -> tuple[int, int] | None:
        """Select the first unresolved cell in top-to-bottom row-major order."""
        for y in range(self.height):
            for x in range(self.width):
                if _bit_count(self._domains[self._cell(x, y)]) > 1:
                    return x, y
        return None

    def context_at(self, x: int, y: int) -> Context:
        values: list[Hashable] = []
        offsets = MOORE if self.decision == "context_moore" else VON_NEUMANN
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.width and 0 <= ny < self.height):
                values.append(UNK)
                continue
            domain = self._domains[self._cell(nx, ny)]
            options = self._domain_values(domain)
            values.append(options[0] if len(options) == 1 else UNK)
        return tuple(values)

    def decision_weights_at(self, x: int, y: int) -> DecisionWeights[Tile]:
        candidates = self.domain_at(x, y)
        if not candidates:
            return DecisionWeights((), ())
        if self.decision == "uniform":
            return DecisionWeights(candidates, (1,) * len(candidates))
        if self.decision == "frequency":
            return DecisionWeights(
                candidates,
                tuple(self.model.frequencies[tile] for tile in candidates),
            )
        contexts = (
            self.model.moore_context_frequencies
            if self.decision == "context_moore"
            else self.model.context_frequencies
        )
        assert contexts is not None
        lookup = contexts.candidate_weights(candidates, self.context_at(x, y))
        self.context_lookups += 1
        self.context_fallbacks += int(lookup.used_frequency_fallback)
        return DecisionWeights(
            candidates,
            lookup.weights,
            used_frequency_fallback=lookup.used_frequency_fallback,
        )

    def collapse_to(self, x: int, y: int, tile: Tile) -> bool:
        """Explicitly observe one legal value, then propagate to fixed point."""
        cell = self._cell(x, y)
        bit = 1 << self._tile_index[tile]
        if not self._domains[cell] & bit:
            raise ValueError(f"tile {tile!r} is not legal at ({x}, {y})")
        self._domains[cell] = bit
        self.observed.add((x, y))
        return self.propagate(((x, y),))

    def observe_next(self) -> bool:
        location = self.select_location()
        if location is None:
            return not self.has_contradiction()
        weights = self.decision_weights_at(*location)
        tile = _weighted_choice(self.random, weights.candidates, weights.weights)
        return self.collapse_to(*location, tile)

    def propagate(self, changed: Sequence[tuple[int, int]]) -> bool:
        """Enforce directional arc support until fixed point or contradiction."""
        queue = deque(changed)
        queued = set(changed)
        while queue:
            x, y = queue.popleft()
            queued.discard((x, y))
            source_domain = self._domains[self._cell(x, y)]
            if source_domain == 0:
                self.contradictions += 1
                return False
            source_values = self._domain_values(source_domain)
            for direction, dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                neighbor_cell = self._cell(nx, ny)
                old_neighbor = self._domains[neighbor_cell]
                supported = 0
                for source in source_values:
                    for neighbor in self.model.adjacency[direction][source]:
                        supported |= 1 << self._tile_index[neighbor]
                new_neighbor = old_neighbor & supported
                if new_neighbor == old_neighbor:
                    continue
                self._domains[neighbor_cell] = new_neighbor
                if new_neighbor == 0:
                    self.contradictions += 1
                    return False
                if (nx, ny) not in queued:
                    queue.append((nx, ny))
                    queued.add((nx, ny))
        return True

    def has_contradiction(self) -> bool:
        return any(domain == 0 for domain in self._domains)

    def is_complete(self) -> bool:
        return not self.has_contradiction() and all(
            _bit_count(domain) == 1 for domain in self._domains
        )

    def run(self) -> WFCResult[Tile]:
        while not self.is_complete():
            if self.has_contradiction() or not self.observe_next():
                break
        output = tuple(
            tuple(
                self.domain_at(x, y)[0] if len(self.domain_at(x, y)) == 1 else None
                for x in range(self.width)
            )
            for y in range(self.height)
        )
        final_domains = tuple(
            tuple(self.domain_at(x, y) for x in range(self.width))
            for y in range(self.height)
        )
        return WFCResult(
            success=self.is_complete(),
            output=output,
            final_domains=final_domains,
            seed=self.seed,
            width=self.width,
            height=self.height,
            selection=self.selection,
            decision=self.decision,
            contradiction_policy="stop",
            attempts=1,
            restarts=0,
            contradictions=self.contradictions,
            observations=len(self.observed),
            context_lookups=self.context_lookups,
            context_fallbacks=self.context_fallbacks,
        )

    def _cell(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"output coordinate is out of bounds: ({x}, {y})")
        return y * self.width + x

    def _domain_values(self, domain: int) -> tuple[Tile, ...]:
        return tuple(
            tile
            for index, tile in enumerate(self.model.tiles)
            if domain & (1 << index)
        )


def _inverse_adjacency(
    tiles: tuple[int, ...],
    forward: Mapping[int, Sequence[int]],
) -> dict[int, tuple[int, ...]]:
    return {
        target: tuple(source for source in tiles if target in forward[source])
        for target in tiles
    }


def _weighted_choice(
    generator: random.Random,
    candidates: tuple[Tile, ...],
    weights: tuple[int, ...],
) -> Tile:
    if not candidates or len(candidates) != len(weights):
        raise ValueError("candidate weights must be nonempty and aligned")
    total = sum(weights)
    if total <= 0:
        raise ValueError("candidate weights must have positive total")
    threshold = generator.random() * total
    cumulative = 0
    for candidate, weight in zip(candidates, weights):
        cumulative += weight
        if threshold < cumulative:
            return candidate
    return candidates[-1]


def _bit_count(value: int) -> int:
    return bin(value).count("1")
