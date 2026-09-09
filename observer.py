"""IPASIR-UP observer that turns placement assignments into domain events."""

from __future__ import annotations

import math
import random
from typing import Callable, Iterable

try:
    from pysat.engines import Propagator
except ImportError:  # Keep pure state tests runnable before optional solver install.
    class Propagator:  # type: ignore[no-redef]
        pass

from trace_format import MappingSpec
from wfc_to_sat.context_frequency import Context, ContextFrequencies, UNK


Emit = Callable[[object], None]


class DomainObserver(Propagator):
    """Track remaining pattern domains and maintain an exact undo trail."""

    def __init__(
        self,
        mapping: MappingSpec,
        emit: Emit,
        heuristic: str = "solver",
        seed: int = 0,
        selection: str = "min_entropy",
        emit_events: bool = True,
        target_houses: int | None = None,
    ) -> None:
        super().__init__()
        if heuristic not in {"solver", "wfc", "uniform", "frequency", "context", "skeleton"}:
            raise ValueError(f"unknown heuristic {heuristic!r}")
        if selection not in {"min_entropy", "lexical"}:
            raise ValueError(f"unknown selection heuristic {selection!r}")
        self.mapping = mapping
        self.emit = emit
        self.emit_events = emit_events
        self.heuristic = heuristic
        self.decision_heuristic = "frequency" if heuristic in {"wfc", "skeleton"} else heuristic
        self.selection_heuristic = selection
        self.random = random.Random(seed)
        self.seed = seed
        self.target_houses = target_houses
        self.pattern_ids = tuple(item.id for item in mapping.patterns)
        self.pattern_index = {pattern_id: i for i, pattern_id in enumerate(self.pattern_ids)}
        self.weights = tuple(item.frequency for item in mapping.patterns)
        self.context_frequencies = (
            ContextFrequencies(mapping.source_pattern_grid)
            if mapping.source_pattern_grid is not None
            else None
        )
        if self.decision_heuristic == "context" and self.context_frequencies is None:
            raise ValueError("context heuristic requires mapping context_data")
        self.full_domain = (1 << len(self.pattern_ids)) - 1
        self.pattern_bits = tuple(1 << index for index in range(len(self.pattern_ids)))
        self.cell_count = mapping.width * mapping.height
        self.domains = [self.full_domain] * self.cell_count
        self.domain_sizes = [len(self.pattern_ids)] * self.cell_count
        self.selected: list[int | None] = [None] * self.cell_count
        self.neighbor_cells = tuple(
            tuple(
                ny * mapping.width + nx
                if 0 <= nx < mapping.width and 0 <= ny < mapping.height else -1
                for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            )
            for y in range(mapping.height)
            for x in range(mapping.width)
        )
        self.current_level = 0
        self.backtrack_events = 0
        self.restart_events = 0
        self.undone_assignments = 0
        self.trails: list[list[tuple[int, int, int | None]]] = [[]]
        self.size_trails: list[list[int]] = [[]]
        self.struct_trails: list[list[tuple[int, bool | None]]] = [[]]
        self.struct_values: dict[int, bool | None] = {}
        self.struct_info: dict[int, tuple[str, dict]] = {}
        if mapping.structural:
            for kind in ("in", "anchor", "counter"):
                for item in mapping.structural.get(kind, []):
                    var = int(item["var"])
                    self.struct_info[var] = (kind, item)
                    self.struct_values[var] = None
        self.in_var_by_cell = {
            (item["x"], item["y"]): var for var, (kind, item) in self.struct_info.items()
            if kind == "in"
        }
        self.var_info: dict[int, tuple[int, int, int, int]] = {}
        self.var_for_cell_pattern: dict[tuple[int, int], int] = {}
        for placement in mapping.placements:
            cell = placement.y * mapping.width + placement.x
            index = self.pattern_index[placement.pattern_id]
            self.var_info[placement.var] = (cell, placement.x, placement.y, index)
            self.var_for_cell_pattern[(cell, index)] = placement.var

    def on_assignment(self, lit: int, fixed: bool = False) -> None:
        info = self.var_info.get(abs(lit))
        if info is None:
            structural = self.struct_info.get(abs(lit))
            if structural is not None:
                self._ensure_level(self.current_level)
                var = abs(lit)
                self.struct_trails[self.current_level].append((var, self.struct_values[var]))
                self.struct_values[var] = lit > 0
                kind, item = structural
                if self.emit_events and kind in {"in", "anchor"}:
                    self.emit(["i" if kind == "in" else "a", item["x"], item["y"], lit > 0, self.current_level])
                elif self.emit_events and kind == "counter" and item.get("output"):
                    self.emit(["c", item["count"], lit > 0, self.current_level])
            return
        cell, x, y, pattern_index = info
        old_domain, old_selected = self.domains[cell], self.selected[cell]
        old_size = self.domain_sizes[cell]
        bit = self.pattern_bits[pattern_index]
        if lit > 0:
            new_domain = bit
            new_size = 1
            new_selected: int | None = pattern_index
        else:
            present = bool(old_domain & bit)
            new_domain = old_domain & ~bit
            new_size = old_size - int(present)
            new_selected = old_selected
        self._ensure_level(self.current_level)
        self.trails[self.current_level].append((cell, old_domain, old_selected))
        self.size_trails[self.current_level].append(old_size)
        self.domains[cell], self.selected[cell], self.domain_sizes[cell] = (
            new_domain, new_selected, new_size,
        )
        if self.emit_events:
            pattern_id = self.pattern_ids[pattern_index]
            if lit > 0:
                self.emit(["p", x, y, pattern_id, self.current_level])
            else:
                self.emit(["n", x, y, pattern_id, self.current_level, new_size])

    def on_new_level(self) -> None:
        self.current_level += 1
        self._ensure_level(self.current_level)
        if self.emit_events:
            self.emit(["l", self.current_level])

    def on_backtrack(self, to: int) -> None:
        if to < 0:
            raise ValueError(f"invalid backtrack level {to}")
        # CaDiCaL may create internal levels containing no observed assignment
        # without an on_new_level callback, then report one of those levels as
        # a later backtrack target.  Such a forward synchronization has no
        # observer trail to undo; retain state and align the next trail level.
        if to > self.current_level:
            self._ensure_level(to)
            self.current_level = to
            if self.emit_events:
                self.emit(["b", to, 0])
            return
        undone = 0
        for level in range(self.current_level, to, -1):
            for (cell, old_domain, old_selected), old_size in zip(
                reversed(self.trails[level]), reversed(self.size_trails[level]),
            ):
                self.domains[cell], self.selected[cell], self.domain_sizes[cell] = (
                    old_domain, old_selected, old_size,
                )
                undone += 1
            self.trails[level].clear()
            self.size_trails[level].clear()
            for var, old_value in reversed(self.struct_trails[level]):
                self.struct_values[var] = old_value
                undone += 1
            self.struct_trails[level].clear()
        self.current_level = to
        self.backtrack_events += 1
        self.undone_assignments += undone
        if self.emit_events:
            self.emit(["b", to, undone])
        if to == 0:
            self.restart_events += 1
            if self.emit_events:
                self.emit(["r", undone])

    def check_model(self, model: list[int]) -> bool:
        positive = {literal for literal in model if literal > 0}
        for cell in range(self.cell_count):
            count = sum(
                self.var_for_cell_pattern[(cell, index)] in positive
                for index in range(len(self.pattern_ids))
            )
            if count != 1:
                return False
        return True

    def decide(self) -> int:
        if self.heuristic == "solver":
            return 0
        if self.heuristic == "skeleton" and self.target_houses is not None:
            anchors = [(var, item) for var, (kind, item) in self.struct_info.items() if kind == "anchor"]
            true_items = [item for var, item in anchors if self.struct_values[var] is True]
            # Re-derive each rectangle from current anchors on every callback.
            # No plan state survives a backjump.
            for item in true_items:
                width = 2 + ((item["x"] * 17 + item["y"] * 7 + self.seed) % 3)
                height = 3 + ((item["x"] * 5 + item["y"] * 11 + self.seed) % 3)
                width = min(width, self.mapping.width - item["x"])
                height = min(height, self.mapping.height - item["y"])
                for y in range(item["y"], item["y"] + height):
                    for x in range(item["x"], item["x"] + width):
                        var = self.in_var_by_cell.get((x, y))
                        if var and self.struct_values[var] is None:
                            return var
                border = (
                    [(item["x"] - 1, y) for y in range(item["y"], item["y"] + height)]
                    + [(item["x"] + width, y) for y in range(item["y"], item["y"] + height)]
                    + [(x, item["y"] - 1) for x in range(item["x"], item["x"] + width)]
                    + [(x, item["y"] + height) for x in range(item["x"], item["x"] + width)]
                )
                for cell in border:
                    var = self.in_var_by_cell.get(cell)
                    if var and self.struct_values[var] is None:
                        return -var
            if len(true_items) < self.target_houses:
                viable = [(var, item) for var, item in anchors if self.struct_values[var] is None
                          and 0 < item["x"] < self.mapping.width - 1
                          and item["y"] + 2 < self.mapping.height]
                if viable:
                    def score(pair):
                        item = pair[1]
                        distance = min((abs(item["x"] - other["x"]) + abs(item["y"] - other["y"])
                                        for other in true_items), default=self.mapping.width + self.mapping.height)
                        return (-distance, self.random.random())
                    return min(viable, key=score)[0]
        if self.selection_heuristic == "lexical":
            cell = next(
                (cell for cell, domain in enumerate(self.domains)
                 if _has_multiple_bits(domain) and self.selected[cell] is None),
                None,
            )
            if cell is None:
                return 0
        else:
            candidates: list[tuple[int, float, float, int]] = []
            for cell, domain in enumerate(self.domains):
                size = _bit_count(domain)
                if size <= 1 or self.selected[cell] is not None:
                    continue
                candidates.append((size, self._entropy(domain), self.random.random(), cell))
            if not candidates:
                return 0
            _, _, _, cell = min(candidates)
        indexes = _set_bit_indexes(self.domains[cell])
        weights = self.decision_weights(cell, indexes)
        chosen = self.random.choices(indexes, weights=weights, k=1)[0]
        return self.var_for_cell_pattern[(cell, chosen)]

    def decision_weights(self, cell: int, indexes: Iterable[int] | None = None) -> tuple[int, ...]:
        """Weights for currently legal candidates at ``cell``."""
        options = tuple(
            indexes if indexes is not None else
            (index for index in range(len(self.pattern_ids)) if self.domains[cell] & (1 << index))
        )
        if self.decision_heuristic == "uniform":
            return (1,) * len(options)
        if self.decision_heuristic in {"frequency", "solver"}:
            return tuple(self.weights[index] for index in options)
        contexts = self.context_frequencies
        assert contexts is not None
        ids = tuple(self.pattern_ids[index] for index in options)
        return contexts.candidate_weights(ids, self.context_at_cell(cell)).weights

    def context_at(self, x: int, y: int) -> Context:
        return self.context_at_cell(y * self.mapping.width + x)

    def context_at_cell(self, cell: int) -> Context:
        def singleton_id(neighbor: int):
            if neighbor < 0:
                return UNK
            domain = self.domains[neighbor]
            if domain == 0 or _has_multiple_bits(domain):
                return UNK
            return self.pattern_ids[domain.bit_length() - 1]

        north, east, south, west = self.neighbor_cells[cell]
        return (
            singleton_id(north), singleton_id(east),
            singleton_id(south), singleton_id(west),
        )

    def propagate(self) -> list[int]:
        return []

    def provide_reason(self, lit: int) -> list[int]:
        return []

    def add_clause(self) -> list[int]:
        return []

    def domain_ids(self, x: int, y: int) -> tuple[int, ...]:
        domain = self.domains[y * self.mapping.width + x]
        return tuple(pattern_id for index, pattern_id in enumerate(self.pattern_ids) if domain & (1 << index))

    def _entropy(self, domain: int) -> float:
        weights = [self.weights[index] for index in range(len(self.weights)) if domain & (1 << index)]
        total = sum(weights)
        return math.log(total) - sum(weight * math.log(weight) for weight in weights) / total

    def _ensure_level(self, level: int) -> None:
        while len(self.trails) <= level:
            self.trails.append([])
            self.size_trails.append([])
            self.struct_trails.append([])


def _bit_count(value: int) -> int:
    return bin(value).count("1")


def _has_multiple_bits(value: int) -> bool:
    return bool(value & (value - 1))


def _set_bit_indexes(value: int) -> list[int]:
    """Return set-bit indexes in the same ascending order as a range scan."""
    indexes = []
    while value:
        lowest = value & -value
        indexes.append(lowest.bit_length() - 1)
        value ^= lowest
    return indexes
