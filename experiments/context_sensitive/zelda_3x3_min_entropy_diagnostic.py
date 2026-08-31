#!/usr/bin/env python3
"""One Context + min-entropy diagnostic on the Zelda 3x3 sequential CNF."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_3x3_sequential_controls import (
    Record,
    build_mapping,
    construct_formula,
)
from observer import DomainObserver


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-sequential/min-entropy-diagnostic"
LOG = OUT / "context-min-entropy-seed-0.log"
RAW = OUT / "context-min-entropy-seed-0.json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    log = LOG.open("w", encoding="utf-8", buffering=1)
    data = {"status": "started", "selection": "min_entropy", "seed": 0}

    def line(message):
        text = f"[{time.perf_counter() - started:.6f}s] {message}"
        print(text, flush=True)
        log.write(text + "\n")
        log.flush()
        data["wall_seconds_so_far"] = time.perf_counter() - started
        RAW.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    line("Context + min-entropy diagnostic (not the required lexical condition)")
    record = Record("context-min-entropy-build")
    _, tile_rgba, patterns, occurrences, allowed, cnf = construct_formula(record)
    data["formula"] = record.data["formula"]

    from pysat.solvers import Cadical195
    line("CaDiCaL bootstrap start")
    stage = time.perf_counter()
    solver = Cadical195(bootstrap_with=cnf.clauses, use_timer=True)
    data["cadical_bootstrap_seconds"] = time.perf_counter() - stage
    line(f"CaDiCaL bootstrap complete: {data['cadical_bootstrap_seconds']:.6f}s")
    observer = None
    try:
        line("mapping construction start")
        stage = time.perf_counter()
        mapping = build_mapping(patterns, occurrences, allowed, cnf, tile_rgba)
        data["mapping_seconds"] = time.perf_counter() - stage
        line(f"mapping construction complete: {data['mapping_seconds']:.6f}s")

        line("DomainObserver Context + min-entropy construction/connection start")
        stage = time.perf_counter()
        observer = DomainObserver(
            mapping, lambda event: None, heuristic="context", seed=0,
            selection="min_entropy",
        )
        solver.connect_propagator(observer)
        data["observer_attach_seconds"] = time.perf_counter() - stage
        line(f"observer construction/connection complete: {data['observer_attach_seconds']:.6f}s")
        if len(observer.var_info) != 1_183_200:
            raise RuntimeError("observer placement-variable set changed")

        line("observe 1,183,200 placement variables start")
        stage = time.perf_counter()
        for placement in mapping.placements:
            solver.observe(placement.var)
        data["observe_seconds"] = time.perf_counter() - stage
        line(f"observe registration complete: {data['observe_seconds']:.6f}s")

        data["solve_entered"] = True
        line("solver.solve() start")
        stage = time.perf_counter()
        sat = solver.solve()
        data["solve_seconds"] = time.perf_counter() - stage
        stats = solver.accum_stats()
        data.update({
            "status": "SAT" if sat else "UNSAT",
            "conflicts": stats.get("conflicts", 0),
            "decisions": stats.get("decisions", 0),
            "observer_backtracks": observer.backtrack_events,
            "undone_assignments": observer.undone_assignments,
        })
        line(f"solver.solve() complete: {data['solve_seconds']:.6f}s; {data['status']}")
    finally:
        if observer is not None:
            solver.disconnect_propagator()
        solver.delete()
        log.close()


if __name__ == "__main__":
    main()
