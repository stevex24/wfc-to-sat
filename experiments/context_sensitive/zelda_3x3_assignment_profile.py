#!/usr/bin/env python3
"""Detailed assignment/undo profile for Zelda 3x3 Context + lexical SAT."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiments.context_sensitive.zelda_3x3_context_profile as base
from experiments.context_sensitive.zelda_3x3_sequential_controls import (
    Record,
    build_mapping,
    construct_formula,
)
from observer import _bit_count, _has_multiple_bits


class AssignmentProfiledObserver(base.ProfiledDomainObserver):
    def __init__(self, *args, **kwargs):
        self.optimized_assignment_profile = kwargs.pop("optimized_assignment_profile")
        super().__init__(*args, **kwargs)
        self.profile.times.update({
            "assignment_mapping_lookup": 0.0,
            "assignment_state_read_decode": 0.0,
            "assignment_membership_test": 0.0,
            "assignment_domain_bit_update": 0.0,
            "assignment_singleton_detection": 0.0,
            "assignment_selected_state": 0.0,
            "assignment_ensure_trail_level": 0.0,
            "assignment_trail_entry_creation": 0.0,
            "assignment_trail_append": 0.0,
            "assignment_state_write": 0.0,
            "assignment_event_domain_size": 0.0,
            "assignment_event_creation": 0.0,
            "assignment_event_emit": 0.0,
            "undo_level_iteration": 0.0,
            "undo_entry_restoration": 0.0,
            "undo_trail_clear": 0.0,
            "undo_event_creation_emit": 0.0,
        })
        self.profile.counts.update({
            "assignment_callbacks": 0,
            "observed_placement_assignments": 0,
            "unmapped_assignment_callbacks": 0,
            "positive_assignments": 0,
            "negative_assignments": 0,
            "domain_noop_assignments": 0,
            "domain_effective_assignments": 0,
            "singleton_transitions": 0,
            "already_singleton_before_assignment": 0,
            "events_emitted": 0,
            "trail_entries_created": 0,
            "undo_entries_restored": 0,
        })

    def on_assignment(self, lit, fixed=False):
        total_started = time.perf_counter()
        self.profile.counts["assignment_callbacks"] += 1

        started = time.perf_counter()
        variable = abs(lit)
        info = self.var_info.get(variable)
        self.profile.times["assignment_mapping_lookup"] += time.perf_counter() - started
        if info is None:
            self.profile.counts["unmapped_assignment_callbacks"] += 1
            self.profile.times["propagation_domain_maintenance_callbacks"] += time.perf_counter() - total_started
            self.profile.snapshot("solving")
            return
        self.profile.counts["observed_placement_assignments"] += 1

        started = time.perf_counter()
        cell, x, y, pattern_index = info
        old_domain = self.domains[cell]
        old_selected = self.selected[cell]
        old_size = self.domain_sizes[cell]
        bit = self.pattern_bits[pattern_index]
        self.profile.times["assignment_state_read_decode"] += time.perf_counter() - started

        started = time.perf_counter()
        was_present = bool(old_domain & bit)
        self.profile.times["assignment_membership_test"] += time.perf_counter() - started

        started = time.perf_counter()
        if lit > 0:
            new_domain = bit
            new_size = 1
            self.profile.counts["positive_assignments"] += 1
        else:
            new_domain = old_domain & ~bit
            new_size = old_size - int(was_present)
            self.profile.counts["negative_assignments"] += 1
        self.profile.times["assignment_domain_bit_update"] += time.perf_counter() - started

        started = time.perf_counter()
        old_singleton = old_domain != 0 and not _has_multiple_bits(old_domain)
        new_singleton = new_domain != 0 and not _has_multiple_bits(new_domain)
        self.profile.times["assignment_singleton_detection"] += time.perf_counter() - started
        if old_singleton:
            self.profile.counts["already_singleton_before_assignment"] += 1
        if not old_singleton and new_singleton:
            self.profile.counts["singleton_transitions"] += 1
        if new_domain == old_domain:
            self.profile.counts["domain_noop_assignments"] += 1
        else:
            self.profile.counts["domain_effective_assignments"] += 1
        # Keep the diagnostic predicate live and check it agrees with the update.
        if lit < 0 and was_present == (new_domain == old_domain):
            raise RuntimeError("membership diagnostic disagrees with domain update")

        started = time.perf_counter()
        new_selected = pattern_index if lit > 0 else old_selected
        self.profile.times["assignment_selected_state"] += time.perf_counter() - started

        started = time.perf_counter()
        self._ensure_level(self.current_level)
        self.profile.times["assignment_ensure_trail_level"] += time.perf_counter() - started
        started = time.perf_counter()
        entry = (cell, old_domain, old_selected)
        self.profile.times["assignment_trail_entry_creation"] += time.perf_counter() - started
        started = time.perf_counter()
        self.trails[self.current_level].append(entry)
        self.profile.times["assignment_trail_append"] += time.perf_counter() - started
        if self.optimized_assignment_profile:
            self.size_trails[self.current_level].append(old_size)
        self.profile.counts["trail_entries_created"] += 1

        started = time.perf_counter()
        self.domains[cell] = new_domain
        self.selected[cell] = new_selected
        if self.optimized_assignment_profile:
            self.domain_sizes[cell] = new_size
        self.profile.times["assignment_state_write"] += time.perf_counter() - started

        pattern_id = self.pattern_ids[pattern_index]
        domain_size = None
        if lit < 0:
            started = time.perf_counter()
            domain_size = new_size if self.optimized_assignment_profile else _bit_count(new_domain)
            self.profile.times["assignment_event_domain_size"] += time.perf_counter() - started
        if self.emit_events:
            started = time.perf_counter()
            event = (
                ["p", x, y, pattern_id, self.current_level]
                if lit > 0 else
                ["n", x, y, pattern_id, self.current_level, domain_size]
            )
            self.profile.times["assignment_event_creation"] += time.perf_counter() - started
            started = time.perf_counter()
            self.emit(event)
            self.profile.times["assignment_event_emit"] += time.perf_counter() - started
            self.profile.counts["events_emitted"] += 1

        self.profile.times["propagation_domain_maintenance_callbacks"] += time.perf_counter() - total_started
        self.profile.snapshot("solving")

    def on_backtrack(self, to):
        total_started = time.perf_counter()
        self.profile.counts["backtrack_callbacks"] += 1
        if to < 0:
            raise ValueError(f"invalid backtrack level {to}")
        if to > self.current_level:
            started = time.perf_counter()
            self._ensure_level(to)
            self.current_level = to
            self.profile.times["undo_level_iteration"] += time.perf_counter() - started
            started = time.perf_counter()
            if self.emit_events:
                self.emit(["b", to, 0])
            self.profile.times["undo_event_creation_emit"] += time.perf_counter() - started
            self.profile.times["undo_backtrack_callbacks"] += time.perf_counter() - total_started
            self.profile.snapshot("solving")
            return

        undone = 0
        for level in range(self.current_level, to, -1):
            started = time.perf_counter()
            entries = self.trails[level]
            self.profile.times["undo_level_iteration"] += time.perf_counter() - started
            size_entries = self.size_trails[level]
            restored = zip(reversed(entries), reversed(size_entries)) if self.optimized_assignment_profile else (
                (entry, None) for entry in reversed(entries)
            )
            for (cell, old_domain, old_selected), old_size in restored:
                started = time.perf_counter()
                self.domains[cell] = old_domain
                self.selected[cell] = old_selected
                if self.optimized_assignment_profile:
                    self.domain_sizes[cell] = old_size
                undone += 1
                self.profile.times["undo_entry_restoration"] += time.perf_counter() - started
            started = time.perf_counter()
            entries.clear()
            if self.optimized_assignment_profile:
                size_entries.clear()
            self.profile.times["undo_trail_clear"] += time.perf_counter() - started
        self.current_level = to
        self.backtrack_events += 1
        self.undone_assignments += undone
        self.profile.counts["undone_assignments"] += undone
        self.profile.counts["undo_entries_restored"] += undone
        started = time.perf_counter()
        if self.emit_events:
            self.emit(["b", to, undone])
        if to == 0:
            self.restart_events += 1
            if self.emit_events:
                self.emit(["r", undone])
        self.profile.times["undo_event_creation_emit"] += time.perf_counter() - started
        self.profile.times["undo_backtrack_callbacks"] += time.perf_counter() - total_started
        self.profile.snapshot("solving")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before-assignment-optimization")
    parser.add_argument("--optimized", action="store_true")
    args = parser.parse_args(argv)
    out = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-sequential/assignment-profile" / args.label
    base.OUT = out
    base.LOG = out / "context-lexical-seed-0.log"
    base.RAW = out / "context-lexical-seed-0.json"

    profile = base.Profile()
    record = Record(f"assignment-profile-{args.label}-build")
    record.line(f"Zelda 3x3 assignment profile: {args.label}")
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
        observer = AssignmentProfiledObserver(
            mapping, lambda event: None, heuristic="context", seed=0,
            selection="lexical", profile=profile,
            emit_events=not args.optimized,
            optimized_assignment_profile=args.optimized,
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
