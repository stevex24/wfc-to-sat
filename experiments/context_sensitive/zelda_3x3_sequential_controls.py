#!/usr/bin/env python3
"""Plain and observer-only controls for the exact Zelda 3x3 sequential CNF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_experiment import tile_source
from experiments.context_sensitive.zelda_3x3_sequential_probe import pattern_rgba
from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import extract_pattern_occurrence_grid


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-sequential/controls"
WIDTH = 20
HEIGHT = 20


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


class Record:
    def __init__(self, mode):
        OUT.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.started = time.perf_counter()
        self.path = OUT / f"{mode}.json"
        self.log = (OUT / f"{mode}.log").open("w", encoding="utf-8", buffering=1)
        self.data = {
            "mode": mode, "status": "started", "timings_seconds": {},
            "formula": {}, "result": {}, "peak_rss_bytes": {},
        }
        self.save()

    def line(self, message):
        text = f"[{time.perf_counter() - self.started:.6f}s] {message}"
        print(text, flush=True)
        self.log.write(text + "\n")
        self.log.flush()

    def timed(self, key, label, function):
        self.line(f"{label} start")
        started = time.perf_counter()
        value = function()
        self.data["timings_seconds"][key] = time.perf_counter() - started
        self.data["peak_rss_bytes"][key] = peak_rss_bytes()
        self.line(f"{label} complete: {self.data['timings_seconds'][key]:.6f}s")
        self.line(f"peak RSS: {peak_rss_bytes()} bytes")
        self.save()
        return value

    def save(self):
        self.data["total_wall_seconds_so_far"] = time.perf_counter() - self.started
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def finish(self):
        self.data["status"] = "completed"
        self.data["timings_seconds"]["total_wall"] = time.perf_counter() - self.started
        self.save()
        self.line(f"total wall-clock complete: {self.data['timings_seconds']['total_wall']:.6f}s")
        self.log.close()


def construct_formula(record):
    source_grid, tile_rgba = record.timed("source_loading", "source tile loading", tile_source)
    patterns, occurrences = record.timed(
        "wrapped_pattern_extraction", "wrapped 3x3 pattern extraction",
        lambda: extract_pattern_occurrence_grid(source_grid, 3, extraction="periodic"),
    )
    allowed = record.timed(
        "compatibility", "overlap compatibility construction",
        lambda: build_compatibility(patterns),
    )
    clause_counts = {}

    def hook(event, stage, cnf):
        if event == "start":
            clause_counts[stage] = len(cnf.clauses)
        else:
            clause_counts[stage] = len(cnf.clauses) - clause_counts[stage]

    cnf = record.timed(
        "cnf_construction", "sequential CNF construction",
        lambda: patterns_to_cnf(
            patterns, allowed, WIDTH, HEIGHT,
            adjacency_encoding="support", exactly_one_encoding="sequential",
            timing_hook=hook,
        ),
    )
    placement_count = len(cnf.name_map)
    formula = {
        "patterns": len(patterns), "placement_variables": placement_count,
        "auxiliary_variables": cnf.num_vars - placement_count,
        "total_variables": cnf.num_vars,
        "exactly_one_clauses": clause_counts["exactly_one"],
        "compatibility_support_clauses": clause_counts["compatibility"],
        "total_clauses": len(cnf.clauses),
    }
    expected = {
        "patterns": 2958, "placement_variables": 1183200,
        "auxiliary_variables": 1182800, "total_variables": 2366000,
        "exactly_one_clauses": 3548400,
        "compatibility_support_clauses": 2248080,
        "total_clauses": 5796480,
    }
    if formula != expected:
        raise RuntimeError(f"formula differs from checkpoint: {formula!r}")
    record.data["formula"] = formula
    for key, value in formula.items(): record.line(f"{key}: {value}")
    record.save()
    return source_grid, tile_rgba, patterns, occurrences, allowed, cnf


def build_mapping(patterns, occurrences, allowed, cnf, tile_rgba):
    specs = tuple(
        PatternSpec(pattern.id, pattern.frequency, 48, 48, pattern_rgba(pattern, tile_rgba))
        for pattern in patterns
    )
    placements = tuple(
        Placement(variable, x, y, pattern_id)
        for variable, (x, y, pattern_id) in cnf.name_map.items()
    )
    mapping = MappingSpec(WIDTH, HEIGHT, specs, placements, allowed, occurrences)
    mapping.validate(num_vars=cnf.num_vars)
    return mapping


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("plain", "observer-solver"))
    args = parser.parse_args(argv)
    record = Record(args.mode)
    record.line(f"Zelda 3x3 sequential control start: {args.mode}")
    _, tile_rgba, patterns, occurrences, allowed, cnf = construct_formula(record)

    from pysat.solvers import Cadical195
    solver = record.timed(
        "cadical_bootstrap", "CaDiCaL bootstrap",
        lambda: Cadical195(bootstrap_with=cnf.clauses, use_timer=True),
    )
    observer = None
    try:
        if args.mode == "plain":
            record.line("DomainObserver attached: False")
            record.data["result"]["observer_attached"] = False
        else:
            mapping = record.timed(
                "mapping_construction", "mapping construction/validation",
                lambda: build_mapping(patterns, occurrences, allowed, cnf, tile_rgba),
            )

            def attach():
                value = DomainObserver(mapping, lambda event: None, heuristic="solver", seed=0)
                solver.connect_propagator(value)
                return value

            observer = record.timed(
                "observer_attach", "DomainObserver solver-mode construction/connection", attach,
            )
            if len(observer.var_info) != len(cnf.name_map) or any(
                variable not in cnf.name_map for variable in observer.var_info
            ):
                raise RuntimeError("observer includes a sequential auxiliary variable")

            def observe_placements():
                for placement in mapping.placements:
                    solver.observe(placement.var)

            record.timed(
                "observe_registration", "placement-only observe() registration",
                observe_placements,
            )
            record.line("DomainObserver attached: True; heuristic=solver; decide() returns 0")
            record.data["result"].update({
                "observer_attached": True,
                "observed_placement_variables": len(mapping.placements),
                "observed_auxiliary_variables": 0,
            })

        record.data["result"]["solve_entered"] = True
        record.save()
        record.line("solver.solve() start")
        started = time.perf_counter()
        sat = solver.solve()
        record.data["timings_seconds"]["solver_solve"] = time.perf_counter() - started
        record.line(f"solver.solve() complete: {record.data['timings_seconds']['solver_solve']:.6f}s")
        stats = solver.accum_stats()
        record.data["result"].update({
            "status": "SAT" if sat else "UNSAT",
            "conflicts": stats.get("conflicts", 0),
            "decisions": stats.get("decisions", 0),
            "observer_backtrack_callbacks": observer.backtrack_events if observer else None,
            "observer_undone_assignments": observer.undone_assignments if observer else None,
        })
        record.finish()
    finally:
        if observer is not None:
            solver.disconnect_propagator()
        solver.delete()


if __name__ == "__main__":
    main()
