#!/usr/bin/env python3
"""Create the requested Zelda 3x3 ordinary-WFC/min-entropy SAT checkpoint."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_experiment import SOURCE, tile_source
from experiments.context_sensitive.zelda_3x3_sequential_probe import (
    decode_patterns,
    kl,
    oriented_distribution,
    pattern_rgba,
    verify_semantics,
)
from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement, clauses_satisfied
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.context_frequency import UNK
from wfc_to_sat.ordinary_wfc import DIRECTIONS, OrdinaryWFC, WFCModel
from wfc_to_sat.patterns import extract_pattern_occurrence_grid


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-visual-checkpoint"
LOG = OUT / "run.log"
RAW = OUT / "results.json"
HTML = OUT / "index.html"
SOURCE_COPY = OUT / "source.png"
WFC_IMAGE = OUT / "ordinary-wfc-context-lexical-seed-0.png"
SAT_IMAGE = OUT / "wfc-as-sat-context-min-entropy-seed-0.png"
WIDTH = HEIGHT = 20
N = 3


class Run:
    def __init__(self, resume=False):
        OUT.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.log = LOG.open("a" if resume else "w", encoding="utf-8", buffering=1)
        self.data = json.loads(RAW.read_text(encoding="utf-8")) if resume else {
            "configuration": {
                "source_extraction": "periodic/wrapped",
                "output_placements": [WIDTH, HEIGHT],
                "pattern_size": N,
                "heuristic": "context",
                "seed": 0,
                "sat_exactly_one": "sequential",
            },
            "ordinary_wfc": {"selection": "lexical", "status": "pending"},
            "wfc_as_sat": {"selection": "min_entropy", "status": "pending"},
            "lexical_sat": {"status": "TIMEOUT", "image": None},
        }
        self.save()

    def line(self, message):
        text = f"[{time.perf_counter() - self.started:.6f}s] {message}"
        print(text, flush=True)
        self.log.write(text + "\n")
        self.log.flush()
        self.save()

    def save(self):
        self.data["total_wall_seconds_so_far"] = time.perf_counter() - self.started
        RAW.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")


class BitmaskOrdinaryWFC(OrdinaryWFC):
    """The reference engine with immutable adjacency masks, not new semantics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._adjacency_masks = {
            direction: {
                tile: sum(1 << self._tile_index[value] for value in options)
                for tile, options in table.items()
            }
            for direction, table in self.model.adjacency.items()
        }

    def select_location(self):
        for cell, domain in enumerate(self._domains):
            if domain & (domain - 1):
                return cell % self.width, cell // self.width
        return None

    def context_at(self, x, y):
        values = []
        for _, dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.width and 0 <= ny < self.height):
                values.append(UNK)
                continue
            domain = self._domains[self._cell(nx, ny)]
            values.append(
                self.model.tiles[domain.bit_length() - 1]
                if domain and not domain & (domain - 1) else UNK
            )
        return tuple(values)

    def propagate(self, changed):
        queue = deque(changed)
        queued = set(changed)
        while queue:
            x, y = queue.popleft()
            queued.discard((x, y))
            source_domain = self._domains[self._cell(x, y)]
            if source_domain == 0:
                self.contradictions += 1
                return False
            for direction, dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                supported = 0
                bits = source_domain
                while bits:
                    lowest = bits & -bits
                    source = self.model.tiles[lowest.bit_length() - 1]
                    supported |= self._adjacency_masks[direction][source]
                    bits ^= lowest
                neighbor_cell = self._cell(nx, ny)
                old_neighbor = self._domains[neighbor_cell]
                new_neighbor = old_neighbor & supported
                if new_neighbor == old_neighbor:
                    continue
                self._domains[neighbor_cell] = new_neighbor
                if new_neighbor == 0:
                    self.contradictions += 1
                    return False
                if (nx, ny) not in queued:
                    queue.append((nx, ny))
                    queued.add((nx, ny))
        return True

def render(decoded, tile_rgba, path):
    image = Image.new("RGBA", (len(decoded[0]) * 16, len(decoded) * 16))
    for y, row in enumerate(decoded):
        for x, tile in enumerate(row):
            image.paste(
                Image.frombytes("RGBA", (16, 16), tile_rgba[ord(tile) - 0x1000]),
                (x * 16, y * 16),
            )
    image.save(path)


def metrics(pattern_grid, decoded, occurrences, source_grid):
    return {
        "pattern_frequency_kl": kl(
            oriented_distribution(pattern_grid), oriented_distribution(occurrences),
        ),
        "pattern_edge_frequency_kl": kl(
            oriented_distribution(pattern_grid, True), oriented_distribution(occurrences, True),
        ),
        "decoded_tile_frequency_kl": kl(
            oriented_distribution(decoded), oriented_distribution(source_grid),
        ),
        "decoded_tile_edge_frequency_kl": kl(
            oriented_distribution(decoded, True), oriented_distribution(source_grid, True),
        ),
    }


def write_html(data):
    def metric_table(record):
        values = record.get("metrics", {})
        if not values:
            return "<p>No metrics: generation did not complete successfully.</p>"
        rows = "".join(
            f"<tr><th>{html.escape(key.replace('_', ' '))}</th><td>{value:.12g}</td></tr>"
            for key, value in values.items()
        )
        return f"<table>{rows}</table>"

    ordinary = data["ordinary_wfc"]
    sat = data["wfc_as_sat"]
    ordinary_image = (
        '<img src="ordinary-wfc-context-lexical-seed-0.png" alt="Ordinary WFC Context lexical seed 0">'
        if ordinary.get("status") == "SAT" else "<div class=missing>No successful image</div>"
    )
    sat_image = (
        '<img src="wfc-as-sat-context-min-entropy-seed-0.png" alt="WFC-as-SAT Context min-entropy diagnostic seed 0">'
        if sat.get("status") == "SAT" else "<div class=missing>No successful image</div>"
    )
    HTML.write_text(f"""<!doctype html><html><head><meta charset=utf-8>
<title>Zelda 3×3 visual checkpoint</title><style>
body{{font:17px/1.5 system-ui;margin:2rem;background:#eef2f7;color:#172033}}main{{max-width:1500px;margin:auto}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:1.5rem}}figure{{margin:0;background:white;border:1px solid #bcc8d8;padding:1rem}}img{{display:block;width:100%;height:auto;image-rendering:pixelated}}figcaption{{font-size:1.15rem;font-weight:700;margin-top:.7rem}}table{{border-collapse:collapse;width:100%;margin-top:1rem}}th,td{{border:1px solid #bcc8d8;padding:.45rem;text-align:left}}td{{font-family:ui-monospace,monospace}}.timeout{{background:#fff1f2;border:2px solid #be123c;padding:1rem;font-weight:700}}.diagnostic{{color:#9a3412}}.missing{{padding:8rem 1rem;text-align:center;background:#e2e8f0}}</style></head>
<body><main><h1>Zelda overlapping 3×3 visual checkpoint</h1>
<p>Seed 0; wrapped source extraction; 20×20 placement grid; Context-sensitive weighting. Generated output boundaries are finite/nonperiodic.</p>
<div class=gallery>
<figure><img src="source.png" alt="Zelda source"><figcaption>Zelda source</figcaption></figure>
<figure>{ordinary_image}<figcaption>Ordinary WFC — Context — LEXICAL</figcaption>{metric_table(ordinary)}<p>Status: {ordinary.get('status')} · runtime: {ordinary.get('runtime_seconds')} s</p></figure>
<figure>{sat_image}<figcaption class=diagnostic>WFC-as-SAT — Context — MIN-ENTROPY DIAGNOSTIC</figcaption>{metric_table(sat)}<p>Status: {sat.get('status')} · solve: {sat.get('solve_seconds')} s · conflicts: {sat.get('conflicts')} · decisions: {sat.get('decisions')} · observer backtracks: {sat.get('observer_backtracks')}</p></figure>
</div><p class=timeout>WFC-as-SAT — Context — LEXICAL: TIMEOUT, no image.</p>
<p><a href="results.json">Raw results JSON</a> · <a href="run.log">Flushed run log</a></p>
</main></body></html>""", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("all", "ordinary", "sat"), default="all")
    args = parser.parse_args(argv)
    run = Run(resume=args.stage == "sat")
    shutil.copyfile(SOURCE, SOURCE_COPY)
    run.line("source loading start")
    source_grid, tile_rgba = tile_source()
    run.line("wrapped 3x3 pattern extraction start")
    patterns, occurrences = extract_pattern_occurrence_grid(source_grid, N, extraction="periodic")
    run.line(f"pattern extraction complete: {len(patterns)} patterns")
    run.line("compatibility construction start")
    allowed = build_compatibility(patterns)
    pattern_by_id = {pattern.id: pattern for pattern in patterns}
    reconstructed_source = tuple(tuple(row) for row in source_grid)
    if tuple(
        tuple(pattern_by_id[occurrences[y][x]].rows[0][0] for x in range(len(source_grid[0])))
        for y in range(len(source_grid))
    ) != reconstructed_source:
        raise RuntimeError("source occurrence-grid reconstruction failed")

    model = WFCModel.from_patterns(patterns, allowed, occurrences)
    if args.stage != "sat":
        run.line("ordinary WFC Context lexical seed 0 start")
        started = time.perf_counter()
        result = BitmaskOrdinaryWFC(
            model, WIDTH, HEIGHT, selection="lexical", decision="context", seed=0,
        ).run()
        ordinary_runtime = time.perf_counter() - started
        ordinary = run.data["ordinary_wfc"]
        ordinary.update({
            "status": "SAT" if result.success else "FAILED",
            "runtime_seconds": ordinary_runtime,
            "observations": result.observations,
            "contradictions": result.contradictions,
        })
        if result.success:
            pattern_grid = tuple(tuple(int(value) for value in row) for row in result.output)
            verify_semantics(pattern_grid, allowed)
            decoded = decode_patterns(pattern_grid, pattern_by_id)
            render(decoded, tile_rgba, WFC_IMAGE)
            ordinary.update({
                "hard_constraints_verified": True,
                "metrics": metrics(pattern_grid, decoded, occurrences, reconstructed_source),
                "image": str(WFC_IMAGE.relative_to(ROOT)),
                "image_sha256": hashlib.sha256(WFC_IMAGE.read_bytes()).hexdigest(),
            })
        run.line(f"ordinary WFC complete: {ordinary['status']} in {ordinary_runtime:.6f}s")
        write_html(run.data)
        if args.stage == "ordinary":
            run.log.close()
            return

    run.line("sequential CNF construction start")
    cnf = patterns_to_cnf(
        patterns, allowed, WIDTH, HEIGHT,
        adjacency_encoding="support", exactly_one_encoding="sequential",
    )
    if (len(cnf.name_map), cnf.num_vars, len(cnf.clauses)) != (1_183_200, 2_366_000, 5_796_480):
        raise RuntimeError("checkpoint formula differs from verified sequential formula")
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

    from pysat.solvers import Cadical195
    run.line("Cadical195 bootstrap start")
    solver = Cadical195(bootstrap_with=cnf.clauses, use_timer=True)
    observer = DomainObserver(
        mapping, lambda event: None, heuristic="context", seed=0,
        selection="min_entropy", emit_events=False,
    )
    solver.connect_propagator(observer)
    for placement in placements:
        solver.observe(placement.var)
    try:
        run.line("WFC-as-SAT Context min-entropy diagnostic solve start")
        started = time.perf_counter()
        sat = solver.solve()
        solve_seconds = time.perf_counter() - started
        stats = solver.accum_stats()
        sat_record = run.data["wfc_as_sat"]
        sat_record.update({
            "status": "SAT" if sat else "UNSAT",
            "solve_seconds": solve_seconds,
            "conflicts": stats.get("conflicts", 0),
            "decisions": stats.get("decisions", 0),
            "observer_backtracks": observer.backtrack_events,
            "undone_assignments": observer.undone_assignments,
        })
        if sat:
            model_values = solver.get_model()
            if not clauses_satisfied(cnf.clauses, model_values):
                raise RuntimeError("returned SAT model does not satisfy the CNF")
            positive = {literal for literal in model_values if literal > 0}
            selected = {
                (x, y): pattern_id
                for variable, (x, y, pattern_id) in cnf.name_map.items()
                if variable in positive
            }
            if len(selected) != WIDTH * HEIGHT:
                raise RuntimeError("SAT model does not select exactly one pattern per cell")
            pattern_grid = tuple(
                tuple(selected[(x, y)] for x in range(WIDTH)) for y in range(HEIGHT)
            )
            verify_semantics(pattern_grid, allowed)
            decoded = decode_patterns(pattern_grid, pattern_by_id)
            render(decoded, tile_rgba, SAT_IMAGE)
            sat_record.update({
                "hard_constraints_verified": True,
                "metrics": metrics(pattern_grid, decoded, occurrences, reconstructed_source),
                "image": str(SAT_IMAGE.relative_to(ROOT)),
                "image_sha256": hashlib.sha256(SAT_IMAGE.read_bytes()).hexdigest(),
            })
        run.line(f"min-entropy SAT complete: {sat_record['status']} in {solve_seconds:.6f}s")
    finally:
        solver.disconnect_propagator()
        solver.delete()

    run.data["status"] = "completed"
    run.save()
    write_html(run.data)
    run.line(f"HTML checkpoint complete: {HTML}")
    run.log.close()


if __name__ == "__main__":
    main()
