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
    ) -> None:
        super().__init__()
        if heuristic not in {"solver", "wfc", "uniform", "frequency", "context"}:
            raise ValueError(f"unknown heuristic {heuristic!r}")
        if selection not in {"min_entropy", "lexical"}:
            raise ValueError(f"unknown selection heuristic {selection!r}")
        self.mapping = mapping
        self.emit = emit
        self.heuristic = heuristic
        self.decision_heuristic = "frequency" if heuristic == "wfc" else heuristic
        self.selection_heuristic = selection
        self.random = random.Random(seed)
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
        self.cell_count = mapping.width * mapping.height
        self.domains = [self.full_domain] * self.cell_count
        self.selected: list[int | None] = [None] * self.cell_count
        self.current_level = 0
        self.backtrack_events = 0
        self.restart_events = 0
        self.undone_assignments = 0
        self.trails: list[list[tuple[int, int, int | None]]] = [[]]
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
            return
        cell, x, y, pattern_index = info
        old_domain, old_selected = self.domains[cell], self.selected[cell]
        if lit > 0:
            new_domain = 1 << pattern_index
            new_selected: int | None = pattern_index
        else:
            new_domain = old_domain & ~(1 << pattern_index)
            new_selected = old_selected
        self._ensure_level(self.current_level)
        self.trails[self.current_level].append((cell, old_domain, old_selected))
        self.domains[cell], self.selected[cell] = new_domain, new_selected
        pattern_id = self.pattern_ids[pattern_index]
        if lit > 0:
            self.emit(["p", x, y, pattern_id, self.current_level])
        else:
            self.emit(["n", x, y, pattern_id, self.current_level, _bit_count(new_domain)])

    def on_new_level(self) -> None:
        self.current_level += 1
        self._ensure_level(self.current_level)
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
            self.emit(["b", to, 0])
            return
        undone = 0
        for level in range(self.current_level, to, -1):
            for cell, old_domain, old_selected in reversed(self.trails[level]):
                self.domains[cell], self.selected[cell] = old_domain, old_selected
                undone += 1
            self.trails[level].clear()
        self.current_level = to
        self.backtrack_events += 1
        self.undone_assignments += undone
        self.emit(["b", to, undone])
        if to == 0:
            self.restart_events += 1
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
        candidates: list[tuple[int, float, float, int]] = []
        for cell, domain in enumerate(self.domains):
            size = _bit_count(domain)
            if size <= 1 or self.selected[cell] is not None:
                continue
            if self.selection_heuristic == "lexical":
                candidates.append((0, 0.0, 0.0, cell))
            else:
                candidates.append((size, self._entropy(domain), self.random.random(), cell))
        if not candidates:
            return 0
        _, _, _, cell = min(candidates)
        indexes = [index for index in range(len(self.pattern_ids)) if self.domains[cell] & (1 << index)]
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
        x, y = cell % self.mapping.width, cell // self.mapping.width
        values = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.mapping.width and 0 <= ny < self.mapping.height):
                values.append(UNK)
                continue
            ids = self.domain_ids(nx, ny)
            values.append(ids[0] if len(ids) == 1 else UNK)
        return (values[0], values[1], values[2], values[3])

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


def _bit_count(value: int) -> int:
    return bin(value).count("1")
