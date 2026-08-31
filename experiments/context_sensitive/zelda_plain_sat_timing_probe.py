#!/usr/bin/env python3
"""One-run plain-CaDiCaL timing control for the Zelda 1x1 CNF."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_timing_probe import tile_source
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
    line(started, "plain CaDiCaL Zelda 1x1 timing control: output=20x20")

    stage = time.perf_counter()
    line(started, "source/model preprocessing start")
    source, _rgba = tile_source()
    model = WFCModel.from_tile_grid(source)
    timings["source_model_preprocessing"] = time.perf_counter() - stage
    line(started, f"source/model preprocessing complete: {timings['source_model_preprocessing']:.6f}s")
    if len(model.tiles) != 90:
        raise RuntimeError(f"expected 90 Zelda tiles, found {len(model.tiles)}")

    tile_id = {tile: index for index, tile in enumerate(model.tiles)}
    patterns = [
        Pattern(tile_id[tile], ((tile,),), model.frequencies[tile])
        for tile in model.tiles
    ]
    allowed = {
        "right": {
            tile_id[t]: [tile_id[v] for v in model.adjacency["east"][t]]
            for t in model.tiles
        },
        "down": {
            tile_id[t]: [tile_id[v] for v in model.adjacency["south"][t]]
            for t in model.tiles
        },
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
        patterns,
        allowed,
        WIDTH,
        HEIGHT,
        adjacency_encoding="support",
        timing_hook=count_clauses,
    )
    timings["cnf_construction"] = time.perf_counter() - stage
    line(started, f"CNF construction complete: {timings['cnf_construction']:.6f}s")
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
    line(started, "domain_observer_attached: False")
    line(started, "solve_entered: True")

    try:
        stage = time.perf_counter()
        line(started, "solver.solve() start")
        sat = solver.solve()
        timings["solve"] = time.perf_counter() - stage
        line(started, f"solver.solve() complete: {timings['solve']:.6f}s")
        line(started, f"solver_result: {'SAT' if sat else 'UNSAT'}")
        stats = solver.accum_stats()
        line(started, f"cadical_conflicts: {stats.get('conflicts', 0)}")
        line(started, f"cadical_decisions: {stats.get('decisions', 0)}")
    finally:
        solver.delete()

    timings["total_wall"] = time.perf_counter() - started
    line(started, f"total wall-clock complete: {timings['total_wall']:.6f}s")
    line(started, "SUMMARY_JSON " + json.dumps({"timings_seconds": timings}, sort_keys=True))


if __name__ == "__main__":
    main()
