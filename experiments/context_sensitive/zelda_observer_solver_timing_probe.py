#!/usr/bin/env python3
"""Time Zelda 1x1 with DomainObserver tracking and CaDiCaL decisions."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_timing_probe import tile_source
from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.ordinary_wfc import WFCModel
from wfc_to_sat.patterns import Pattern


WIDTH = 20
HEIGHT = 20


def line(started, message):
    print(f"[{time.perf_counter() - started:.6f}s] {message}", flush=True)


def main():
    started = time.perf_counter()
    timings = {}
    line(started, "Zelda 1x1 observer/solver-decision timing control: output=20x20")

    stage = time.perf_counter()
    line(started, "source/model preprocessing start")
    source, rgba = tile_source()
    model = WFCModel.from_tile_grid(source)
    timings["source_model_preprocessing"] = time.perf_counter() - stage
    line(started, f"source/model preprocessing complete: {timings['source_model_preprocessing']:.6f}s")
    if len(model.tiles) != 90:
        raise RuntimeError(f"expected 90 Zelda tiles, found {len(model.tiles)}")

    tile_id = {tile: index for index, tile in enumerate(model.tiles)}
    patterns = [Pattern(tile_id[t], ((t,),), model.frequencies[t]) for t in model.tiles]
    allowed = {
        "right": {tile_id[t]: [tile_id[v] for v in model.adjacency["east"][t]] for t in model.tiles},
        "down": {tile_id[t]: [tile_id[v] for v in model.adjacency["south"][t]] for t in model.tiles},
    }
    clause_counts = {}

    def count_clauses(event, stage_name, cnf):
        if event == "start":
            clause_counts[stage_name] = len(cnf.clauses)
        else:
            clause_counts[stage_name] = len(cnf.clauses) - clause_counts[stage_name]

    stage = time.perf_counter()
    line(started, "CNF construction start")
    cnf = patterns_to_cnf(
        patterns, allowed, WIDTH, HEIGHT,
        adjacency_encoding="support", timing_hook=count_clauses,
    )
    timings["cnf_construction"] = time.perf_counter() - stage
    line(started, f"CNF construction complete: {timings['cnf_construction']:.6f}s")

    stage = time.perf_counter()
    line(started, "mapping construction start")
    specs = tuple(
        PatternSpec(tile_id[t], model.frequencies[t], 16, 16, rgba[tile_id[t]])
        for t in model.tiles
    )
    placements = tuple(
        Placement(var, x, y, pattern_id)
        for var, (x, y, pattern_id) in sorted(cnf.name_map.items())
    )
    mapping = MappingSpec(
        WIDTH, HEIGHT, specs, placements, allowed,
        tuple(tuple(tile_id[t] for t in row) for row in model.context_frequencies.source_grid),
    )
    mapping.validate(num_vars=cnf.num_vars)
    timings["mapping_construction"] = time.perf_counter() - stage
    line(started, f"mapping construction complete: {timings['mapping_construction']:.6f}s")
    line(started, f"sat_variables: {cnf.num_vars}")
    line(started, f"exactly_one_clauses: {clause_counts['exactly_one']}")
    line(started, f"compatibility_clauses: {clause_counts['compatibility']}")
    line(started, f"total_clauses: {len(cnf.clauses)}")

    from pysat.solvers import Cadical195

    stage = time.perf_counter()
    line(started, "CaDiCaL bootstrap start")
    solver = Cadical195(bootstrap_with=cnf.clauses, use_timer=True)
    timings["cadical_bootstrap"] = time.perf_counter() - stage
    line(started, f"CaDiCaL bootstrap complete: {timings['cadical_bootstrap']:.6f}s")

    try:
        stage = time.perf_counter()
        line(started, "DomainObserver solver-mode construction/connection start")
        observer = DomainObserver(mapping, lambda event: None, heuristic="solver", seed=0)
        solver.connect_propagator(observer)
        timings["observer_attach"] = time.perf_counter() - stage
        line(started, f"DomainObserver solver-mode construction/connection complete: {timings['observer_attach']:.6f}s")
        line(started, "domain_observer_attached: True")
        line(started, "observer_heuristic: solver (decide returns 0; CaDiCaL chooses)")

        stage = time.perf_counter()
        line(started, "observed-variable registration start")
        for placement in mapping.placements:
            solver.observe(placement.var)
        timings["observe_variables"] = time.perf_counter() - stage
        line(started, f"observed-variable registration complete: {timings['observe_variables']:.6f}s")
        line(started, f"observed_variables: {len(mapping.placements)}")
        line(started, "solve_entered: True")

        stage = time.perf_counter()
        line(started, "solver.solve() start")
        sat = solver.solve()
        timings["solve"] = time.perf_counter() - stage
        line(started, f"solver.solve() complete: {timings['solve']:.6f}s")
        line(started, f"solver_result: {'SAT' if sat else 'UNSAT'}")
        stats = solver.accum_stats()
        line(started, f"cadical_conflicts: {stats.get('conflicts', 0)}")
        line(started, f"cadical_decisions: {stats.get('decisions', 0)}")
        line(started, f"observer_backtrack_callbacks: {observer.backtrack_events}")
        line(started, f"observer_undone_assignments: {observer.undone_assignments}")
    finally:
        solver.disconnect_propagator()
        solver.delete()

    timings["total_wall"] = time.perf_counter() - started
    line(started, f"total wall-clock complete: {timings['total_wall']:.6f}s")
    line(started, "SUMMARY_JSON " + json.dumps({"timings_seconds": timings}, sort_keys=True))


if __name__ == "__main__":
    main()
