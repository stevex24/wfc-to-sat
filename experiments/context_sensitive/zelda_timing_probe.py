#!/usr/bin/env python3
"""One-run, stage-timed Zelda 1x1 SAT diagnostic."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.ordinary_wfc import WFCModel
from wfc_to_sat.patterns import Pattern


SOURCE = ROOT / "examples/context-sensitive/zelda-map-authors.png"
LOG = ROOT / "context-sensitive-results/detailed-comparison/raw/zelda-1x1-timing-probe.log"
WIDTH = 20
HEIGHT = 20
SEED = 0
HEURISTIC = "uniform"
SELECTION = "lexical"


class Probe:
    def __init__(self):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.stage_starts = {}
        self.timings = {}
        self.values = {}
        self.log_file = LOG.open("w", encoding="utf-8", buffering=1)

    def line(self, message):
        line = f"[{time.perf_counter() - self.started:.6f}s] {message}"
        print(line, flush=True)
        self.log_file.write(line + "\n")
        self.log_file.flush()

    def start(self, stage, label=None):
        self.line(f"{label or stage} start")
        self.stage_starts[stage] = time.perf_counter()

    def end(self, stage, label=None):
        elapsed = time.perf_counter() - self.stage_starts[stage]
        self.timings[stage] = elapsed
        self.line(f"{label or stage} complete: {elapsed:.6f}s")
        return elapsed

    def record(self, key, value):
        self.values[key] = value
        self.line(f"{key}: {value}")

    def close(self):
        self.log_file.close()


def tile_source(path=SOURCE, tile_size=16):
    image = Image.open(path).convert("RGBA")
    if image.width % tile_size or image.height % tile_size:
        raise ValueError("Zelda source dimensions are not divisible by 16")
    ids, tiles, rows = {}, [], []
    for y in range(0, image.height, tile_size):
        row = []
        for x in range(0, image.width, tile_size):
            rgba = image.crop((x, y, x + tile_size, y + tile_size)).tobytes()
            if rgba not in ids:
                ids[rgba] = len(tiles)
                tiles.append(rgba)
            row.append(chr(0x1000 + ids[rgba]))
        rows.append("".join(row))
    return tuple(rows), tuple(tiles)


def main():
    probe = Probe()
    probe.line("Zelda 1x1 timing probe: seed=0 heuristic=uniform selection=lexical output=20x20")
    probe.start("source", "source preprocessing")
    source, rgba = tile_source()
    probe.end("source", "source preprocessing")

    probe.start("model", "model / adjacency / context construction")
    model = WFCModel.from_tile_grid(source)
    probe.end("model", "model / adjacency / context construction")
    if len(model.tiles) != 90:
        raise RuntimeError(f"expected 90 Zelda tiles, found {len(model.tiles)}")

    tile_id = {tile: index for index, tile in enumerate(model.tiles)}
    patterns = [Pattern(tile_id[tile], ((tile,),), model.frequencies[tile]) for tile in model.tiles]
    allowed = {
        "right": {tile_id[t]: [tile_id[v] for v in model.adjacency["east"][t]] for t in model.tiles},
        "down": {tile_id[t]: [tile_id[v] for v in model.adjacency["south"][t]] for t in model.tiles},
    }

    clause_counts = {}
    def cnf_timing(event, stage, cnf):
        if event == "start":
            clause_counts[stage] = len(cnf.clauses)
            probe.start(f"cnf_{stage}", {
                "variables": "SAT variable allocation",
                "exactly_one": "exactly-one clause construction",
                "compatibility": "compatibility/support clause construction",
            }[stage])
        else:
            probe.end(f"cnf_{stage}", {
                "variables": "SAT variable allocation",
                "exactly_one": "exactly-one clause construction",
                "compatibility": "compatibility/support clause construction",
            }[stage])
            clause_counts[stage] = len(cnf.clauses) - clause_counts[stage]

    probe.start("cnf_total", "total CNF construction")
    cnf = patterns_to_cnf(
        patterns, allowed, WIDTH, HEIGHT,
        adjacency_encoding="support", timing_hook=cnf_timing,
    )
    probe.end("cnf_total", "total CNF construction")

    probe.start("mapping", "mapping construction")
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
    tile_for_id = {index: tile for tile, index in tile_id.items()}
    probe.end("mapping", "mapping construction")

    probe.record("candidates_per_cell", len(patterns))
    probe.record("output_cells", WIDTH * HEIGHT)
    probe.record("sat_variables", cnf.num_vars)
    probe.record("exactly_one_clauses", clause_counts["exactly_one"])
    probe.record("compatibility_clauses", clause_counts["compatibility"])
    probe.record("total_clauses", len(cnf.clauses))

    from pysat.solvers import Cadical195
    probe.start("cadical_bootstrap", "CaDiCaL bootstrap")
    solver = Cadical195(bootstrap_with=cnf.clauses, use_timer=True)
    probe.end("cadical_bootstrap", "CaDiCaL bootstrap")
    try:
        probe.start("observer_attach", "DomainObserver instantiate/connect")
        observer = DomainObserver(
            mapping, lambda event: None, heuristic=HEURISTIC,
            seed=SEED, selection=SELECTION,
        )
        solver.connect_propagator(observer)
        probe.end("observer_attach", "DomainObserver instantiate/connect")
        probe.record("domain_observer_attached", True)

        probe.start("observe_variables", "observed-variable registration")
        for placement in mapping.placements:
            solver.observe(placement.var)
        probe.end("observe_variables", "observed-variable registration")
        probe.record("observed_variables", len(mapping.placements))

        probe.record("solve_entered", True)
        probe.start("solve", "solver.solve()")
        sat = solver.solve()
        probe.end("solve", "solver.solve()")
        probe.record("solver_result", "SAT" if sat else "UNSAT")
        stats = solver.accum_stats()
        probe.record("cadical_conflicts", stats.get("conflicts", 0))
        probe.record("cadical_decisions", stats.get("decisions", 0))
        probe.record("observer_backtrack_callbacks", observer.backtrack_events)

        probe.start("post_solve", "post-solve decode")
        sat_model = solver.get_model() if sat else []
        positive = {literal for literal in (sat_model or []) if literal > 0}
        output = []
        if sat:
            by_cell = {(p.x, p.y): [] for p in mapping.placements}
            for placement in mapping.placements:
                if placement.var in positive:
                    by_cell[(placement.x, placement.y)].append(placement.pattern_id)
            for y in range(HEIGHT):
                row = []
                for x in range(WIDTH):
                    found = by_cell[(x, y)]
                    if len(found) != 1:
                        raise RuntimeError("SAT model does not contain exactly one pattern per cell")
                    row.append(tile_for_id[found[0]])
                output.append(row)
        probe.end("post_solve", "post-solve decode")
    finally:
        solver.disconnect_propagator()
        solver.delete()

    probe.timings["total_wall"] = time.perf_counter() - probe.started
    probe.line(f"total wall-clock complete: {probe.timings['total_wall']:.6f}s")
    probe.line("SUMMARY_JSON " + json.dumps({"timings_seconds": probe.timings, **probe.values}, sort_keys=True))
    probe.close()


if __name__ == "__main__":
    main()
