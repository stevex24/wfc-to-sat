#!/usr/bin/env python3
"""One-run Zelda 1x1 timing probe for frequency or context decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from PIL import Image

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
SEED = 0
RAW = ROOT / "context-sensitive-results/detailed-comparison/raw"
IMAGES = ROOT / "context-sensitive-results/detailed-comparison/images"


class Log:
    def __init__(self, heuristic):
        RAW.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.file = (RAW / f"zelda-1x1-{heuristic}-timing-probe.log").open(
            "w", encoding="utf-8", buffering=1
        )

    def line(self, message):
        text = f"[{time.perf_counter() - self.started:.6f}s] {message}"
        print(text, flush=True)
        self.file.write(text + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--heuristic", required=True, choices=("frequency", "context"))
    args = parser.parse_args(argv)
    heuristic = args.heuristic
    log = Log(heuristic)
    timings = {}
    log.line(f"Zelda 1x1 timing probe: seed=0 heuristic={heuristic} selection=lexical output=20x20")

    stage = time.perf_counter()
    log.line("source/model preprocessing start")
    source, rgba = tile_source()
    model = WFCModel.from_tile_grid(source)
    timings["source_model_preprocessing"] = time.perf_counter() - stage
    log.line(f"source/model preprocessing complete: {timings['source_model_preprocessing']:.6f}s")
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
    log.line("CNF construction start")
    cnf = patterns_to_cnf(
        patterns, allowed, WIDTH, HEIGHT,
        adjacency_encoding="support", timing_hook=count_clauses,
    )
    timings["cnf_construction"] = time.perf_counter() - stage
    log.line(f"CNF construction complete: {timings['cnf_construction']:.6f}s")

    stage = time.perf_counter()
    log.line("mapping construction start")
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
    log.line(f"mapping construction complete: {timings['mapping_construction']:.6f}s")
    log.line(f"sat_variables: {cnf.num_vars}")
    log.line(f"exactly_one_clauses: {clause_counts['exactly_one']}")
    log.line(f"compatibility_clauses: {clause_counts['compatibility']}")
    log.line(f"total_clauses: {len(cnf.clauses)}")

    from pysat.solvers import Cadical195

    stage = time.perf_counter()
    log.line("CaDiCaL bootstrap start")
    solver = Cadical195(bootstrap_with=cnf.clauses, use_timer=True)
    timings["cadical_bootstrap"] = time.perf_counter() - stage
    log.line(f"CaDiCaL bootstrap complete: {timings['cadical_bootstrap']:.6f}s")
    try:
        stage = time.perf_counter()
        log.line("DomainObserver construction/connection start")
        observer = DomainObserver(
            mapping, lambda event: None, heuristic=heuristic,
            seed=SEED, selection="lexical",
        )
        solver.connect_propagator(observer)
        timings["observer_attach"] = time.perf_counter() - stage
        log.line(f"DomainObserver construction/connection complete: {timings['observer_attach']:.6f}s")
        log.line("domain_observer_attached: True")

        stage = time.perf_counter()
        log.line("observed-variable registration start")
        for placement in mapping.placements:
            solver.observe(placement.var)
        timings["observe_variables"] = time.perf_counter() - stage
        log.line(f"observed-variable registration complete: {timings['observe_variables']:.6f}s")
        log.line(f"observed_variables: {len(mapping.placements)}")
        log.line("solve_entered: True")

        stage = time.perf_counter()
        log.line("solver.solve() start")
        sat = solver.solve()
        timings["solve"] = time.perf_counter() - stage
        log.line(f"solver.solve() complete: {timings['solve']:.6f}s")
        log.line(f"solver_result: {'SAT' if sat else 'UNSAT'}")
        stats = solver.accum_stats()
        log.line(f"cadical_conflicts: {stats.get('conflicts', 0)}")
        log.line(f"cadical_decisions: {stats.get('decisions', 0)}")
        log.line(f"observer_backtrack_callbacks: {observer.backtrack_events}")

        if sat:
            stage = time.perf_counter()
            log.line("decode/render start")
            positive = {literal for literal in solver.get_model() if literal > 0}
            chosen = {(p.x, p.y): p.pattern_id for p in placements if p.var in positive}
            if len(chosen) != WIDTH * HEIGHT:
                raise RuntimeError("SAT model does not contain exactly one pattern per cell")
            image = Image.new("RGBA", (WIDTH * 16, HEIGHT * 16))
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    tile = Image.frombytes("RGBA", (16, 16), rgba[chosen[(x, y)]])
                    image.paste(tile, (x * 16, y * 16))
            IMAGES.mkdir(parents=True, exist_ok=True)
            image_path = IMAGES / f"zelda-1x1-{heuristic}-sat-seed-0-timing-probe.png"
            image.save(image_path)
            timings["decode_render"] = time.perf_counter() - stage
            log.line(f"decode/render complete: {timings['decode_render']:.6f}s")
            log.line(f"output_image: {image_path.relative_to(ROOT)}")
    finally:
        solver.disconnect_propagator()
        solver.delete()

    timings["total_wall"] = time.perf_counter() - log.started
    log.line(f"total wall-clock complete: {timings['total_wall']:.6f}s")
    log.line("SUMMARY_JSON " + json.dumps({"heuristic": heuristic, "timings_seconds": timings}, sort_keys=True))
    log.close()


if __name__ == "__main__":
    main()
