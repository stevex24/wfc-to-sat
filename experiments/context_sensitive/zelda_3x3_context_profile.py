#!/usr/bin/env python3
"""Profile one unchanged Zelda 3x3 context/lexical sequential SAT run."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_3x3_sequential_controls import (
    HEIGHT,
    WIDTH,
    Record,
    build_mapping,
    construct_formula,
)
from observer import DomainObserver, _bit_count


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-sequential/profile"
LOG = OUT / "context-lexical-seed-0.log"
RAW = OUT / "context-lexical-seed-0.json"


class Profile:
    def __init__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.solve_started = None
        self.last_flush = 0.0
        self.times = {
            "decide_total": 0.0,
            "lexical_cell_selection": 0.0,
            "candidate_enumeration_domain_scanning": 0.0,
            "context_construction_nesw": 0.0,
            "context_candidate_weights": 0.0,
            "weighted_random_choice": 0.0,
            "propagation_domain_maintenance_callbacks": 0.0,
            "undo_backtrack_callbacks": 0.0,
        }
        self.counts = {
            "decide_callbacks": 0,
            "wfc_decisions_supplied": 0,
            "domain_evaluations": 0,
            "domain_size_sum": 0,
            "domain_size_max": 0,
            "frequency_fallbacks": 0,
            "backtrack_callbacks": 0,
            "undone_assignments": 0,
        }
        self.reached_cells = set()
        self.log = LOG.open("w", encoding="utf-8", buffering=1)

    def snapshot(self, label, force=False):
        now = time.perf_counter()
        if not force and now - self.last_flush < 5.0:
            return
        self.last_flush = now
        evaluations = self.counts["domain_evaluations"]
        fallbacks = self.counts["frequency_fallbacks"]
        decisions = self.counts["wfc_decisions_supplied"]
        data = {
            "status": label,
            "wall_seconds": now - self.started,
            "solve_seconds_so_far": None if self.solve_started is None else now - self.solve_started,
            "cumulative_seconds": self.times,
            "counts": self.counts,
            "average_domain_size_evaluated": (
                self.counts["domain_size_sum"] / evaluations if evaluations else None
            ),
            "max_domain_size_evaluated": self.counts["domain_size_max"] if evaluations else None,
            "fallback_rate": fallbacks / decisions if decisions else None,
            "lexical_cells_reached": len(self.reached_cells),
            "lexical_cell_indexes_reached": sorted(self.reached_cells),
        }
        line = f"[{now - self.started:.6f}s] PROFILE {json.dumps(data, sort_keys=True)}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()
        RAW.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ProfiledDomainObserver(DomainObserver):
    def __init__(self, *args, profile, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)

    def on_assignment(self, lit, fixed=False):
        started = time.perf_counter()
        try:
            return super().on_assignment(lit, fixed)
        finally:
            self.profile.times["propagation_domain_maintenance_callbacks"] += time.perf_counter() - started
            self.profile.snapshot("solving")

    def on_new_level(self):
        started = time.perf_counter()
        try:
            return super().on_new_level()
        finally:
            self.profile.times["propagation_domain_maintenance_callbacks"] += time.perf_counter() - started
            self.profile.snapshot("solving")

    def propagate(self):
        started = time.perf_counter()
        try:
            return super().propagate()
        finally:
            self.profile.times["propagation_domain_maintenance_callbacks"] += time.perf_counter() - started
            self.profile.snapshot("solving")

    def on_backtrack(self, to):
        started = time.perf_counter()
        before = self.undone_assignments
        try:
            return super().on_backtrack(to)
        finally:
            self.profile.times["undo_backtrack_callbacks"] += time.perf_counter() - started
            self.profile.counts["backtrack_callbacks"] += 1
            self.profile.counts["undone_assignments"] += self.undone_assignments - before
            self.profile.snapshot("solving")

    def decide(self):
        total_started = time.perf_counter()
        self.profile.counts["decide_callbacks"] += 1
        try:
            # This is the existing lexical/context decision path split only at
            # its current operation boundaries for timing.
            started = time.perf_counter()
            candidates = []
            for cell, domain in enumerate(self.domains):
                size = _bit_count(domain)
                if size <= 1 or self.selected[cell] is not None:
                    continue
                candidates.append((0, 0.0, 0.0, cell))
            if not candidates:
                self.profile.times["lexical_cell_selection"] += time.perf_counter() - started
                return 0
            _, _, _, cell = min(candidates)
            self.profile.times["lexical_cell_selection"] += time.perf_counter() - started
            self.profile.reached_cells.add(cell)

            started = time.perf_counter()
            indexes = [
                index for index in range(len(self.pattern_ids))
                if self.domains[cell] & (1 << index)
            ]
            ids = tuple(self.pattern_ids[index] for index in indexes)
            self.profile.times["candidate_enumeration_domain_scanning"] += time.perf_counter() - started
            size = len(indexes)
            self.profile.counts["domain_evaluations"] += 1
            self.profile.counts["domain_size_sum"] += size
            self.profile.counts["domain_size_max"] = max(self.profile.counts["domain_size_max"], size)

            started = time.perf_counter()
            context = self.context_at_cell(cell)
            self.profile.times["context_construction_nesw"] += time.perf_counter() - started

            started = time.perf_counter()
            lookup = self.context_frequencies.candidate_weights(ids, context)
            self.profile.times["context_candidate_weights"] += time.perf_counter() - started
            if lookup.used_frequency_fallback:
                self.profile.counts["frequency_fallbacks"] += 1

            started = time.perf_counter()
            chosen = self.random.choices(indexes, weights=lookup.weights, k=1)[0]
            self.profile.times["weighted_random_choice"] += time.perf_counter() - started
            self.profile.counts["wfc_decisions_supplied"] += 1
            return self.var_for_cell_pattern[(cell, chosen)]
        finally:
            self.profile.times["decide_total"] += time.perf_counter() - total_started
            self.profile.snapshot("solving")


def main():
    profile = Profile()
    record = Record("context-profile-build")
    record.line("Zelda 3x3 Context lexical sequential profiling probe")
    _, tile_rgba, patterns, occurrences, allowed, cnf = construct_formula(record)

    from pysat.solvers import Cadical195
    solver = record.timed(
        "cadical_bootstrap", "CaDiCaL bootstrap",
        lambda: Cadical195(bootstrap_with=cnf.clauses, use_timer=True),
    )
    observer = None
    try:
        mapping = record.timed(
            "mapping_construction", "mapping construction/validation",
            lambda: build_mapping(patterns, occurrences, allowed, cnf, tile_rgba),
        )
        observer = ProfiledDomainObserver(
            mapping, lambda event: None, heuristic="context", seed=0,
            selection="lexical", profile=profile,
        )
        solver.connect_propagator(observer)
        if len(observer.var_info) != 1_183_200:
            raise RuntimeError("observer placement-variable set changed")
        for placement in mapping.placements:
            solver.observe(placement.var)
        record.line("DomainObserver attached; 1,183,200 placement variables observed; solve start")
        profile.solve_started = time.perf_counter()
        profile.snapshot("solve_entered", force=True)
        sat = solver.solve()
        profile.snapshot("SAT" if sat else "UNSAT", force=True)
    finally:
        if observer is not None:
            solver.disconnect_propagator()
        solver.delete()
        profile.log.close()
        record.log.close()


if __name__ == "__main__":
    main()
