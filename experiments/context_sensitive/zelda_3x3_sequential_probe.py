#!/usr/bin/env python3
"""Construct and, if practical, solve one sequential-encoded Zelda 3x3 instance."""

from __future__ import annotations

from collections import Counter
import argparse
import json
import math
from pathlib import Path
import resource
import shutil
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_experiment import SOURCE, tile_source
from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import extract_pattern_occurrence_grid


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3-sequential"
LOG = OUT / "context-seed-0-timing.log"
RAW = OUT / "context-seed-0.json"
IMAGE = OUT / "context-seed-0.png"
CHECKPOINT = OUT / "index.html"
WIDTH = 20
HEIGHT = 20
PATTERN_SIZE = 3


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


class Probe:
    def __init__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.timings = {}
        self.data = {
            "configuration": {
                "source": str(SOURCE.relative_to(ROOT)), "pattern_size": 3,
                "source_extraction": "periodic", "output": "20x20 placements",
                "output_boundary": "finite/nonperiodic", "seed": 0,
                "heuristic": "context", "selection": "lexical",
                "solver": "PySAT Cadical195 + DomainObserver",
                "adjacency_encoding": "support",
                "exactly_one_encoding": "sequential",
            },
            "status": "started", "formula": {}, "timings_seconds": self.timings,
            "result": {}, "metrics": {},
        }
        self.file = LOG.open("w", encoding="utf-8", buffering=1)
        self.save()

    def line(self, message):
        text = f"[{time.perf_counter() - self.started:.6f}s] {message}"
        print(text, flush=True)
        self.file.write(text + "\n")
        self.file.flush()

    def timed(self, name, label, function):
        self.line(f"{label} start")
        started = time.perf_counter()
        value = function()
        self.timings[name] = time.perf_counter() - started
        self.line(f"{label} complete: {self.timings[name]:.6f}s")
        self.record_memory(label)
        self.save()
        return value

    def record_memory(self, label):
        self.data.setdefault("peak_rss_bytes", {})[label] = peak_rss_bytes()
        self.line(f"peak RSS after {label}: {peak_rss_bytes()} bytes")

    def save(self):
        self.data["total_wall_seconds_so_far"] = time.perf_counter() - self.started
        RAW.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def finish(self, status):
        self.data["status"] = status
        self.timings["total_wall"] = time.perf_counter() - self.started
        self.save()
        self.line(f"status: {status}")
        self.line(f"total wall-clock: {self.timings['total_wall']:.6f}s")
        self.file.close()


def pattern_rgba(pattern, tile_rgba):
    image = Image.new("RGBA", (PATTERN_SIZE * 16, PATTERN_SIZE * 16))
    for dy, row in enumerate(pattern.rows):
        for dx, tile in enumerate(row):
            image.paste(Image.frombytes("RGBA", (16, 16), tile_rgba[ord(tile) - 0x1000]), (dx * 16, dy * 16))
    return image.tobytes()


def oriented_distribution(rows, edge=False):
    counts = Counter()
    if edge:
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                if x + 1 < len(row): counts[("H", value, row[x + 1])] += 1
                if y + 1 < len(rows): counts[("V", value, rows[y + 1][x])] += 1
    else:
        counts.update(value for row in rows for value in row)
    total = sum(counts.values())
    return {key: value / total for key, value in counts.items()}


def kl(target, source):
    if any(source.get(key, 0.0) == 0.0 for key in target):
        return math.inf
    return sum(value * math.log(value / source[key]) for key, value in target.items())


def decode_patterns(pattern_grid, patterns_by_id):
    decoded = [[None] * (WIDTH + PATTERN_SIZE - 1) for _ in range(HEIGHT + PATTERN_SIZE - 1)]
    for y, row in enumerate(pattern_grid):
        for x, pattern_id in enumerate(row):
            pattern = patterns_by_id[pattern_id]
            for dy in range(PATTERN_SIZE):
                for dx in range(PATTERN_SIZE):
                    value = pattern.rows[dy][dx]
                    old = decoded[y + dy][x + dx]
                    if old is not None and old != value:
                        raise RuntimeError("overlapping pattern decode is inconsistent")
                    decoded[y + dy][x + dx] = value
    if any(value is None for row in decoded for value in row):
        raise RuntimeError("decoded tile grid has a gap")
    return tuple(tuple(row) for row in decoded)


def verify_semantics(pattern_grid, allowed):
    for y, row in enumerate(pattern_grid):
        for x, pattern_id in enumerate(row):
            if x + 1 < WIDTH and row[x + 1] not in allowed["right"][pattern_id]:
                raise RuntimeError("decoded model violates right compatibility")
            if y + 1 < HEIGHT and pattern_grid[y + 1][x] not in allowed["down"][pattern_id]:
                raise RuntimeError("decoded model violates down compatibility")


def render(decoded, tile_rgba):
    image = Image.new("RGBA", (len(decoded[0]) * 16, len(decoded) * 16))
    for y, row in enumerate(decoded):
        for x, tile in enumerate(row):
            image.paste(Image.frombytes("RGBA", (16, 16), tile_rgba[ord(tile) - 0x1000]), (x * 16, y * 16))
    image.save(IMAGE)


def write_checkpoint(data):
    shutil.copyfile(SOURCE, OUT / "source.png")
    formula, timings, result, metrics = data["formula"], data["timings_seconds"], data["result"], data["metrics"]
    image_html = "<figure><img src=source.png><figcaption>Zelda source; no generated output because solve timed out.</figcaption></figure>"
    if IMAGE.exists():
        image_html = "<div class=grid><figure><img src=source.png><figcaption>Zelda source</figcaption></figure><figure><img src=context-seed-0.png><figcaption>Context WFC-as-SAT · seed 0 · sequential exactly-one</figcaption></figure></div>"
    metric_rows = "".join(f"<tr><td>{name.replace('_', ' ')}</td><td>{value}</td></tr>" for name, value in metrics.items())
    CHECKPOINT.write_text(f"""<!doctype html><html><head><meta charset=utf-8><title>Zelda 3x3 sequential probe</title><style>body{{font:16px/1.5 system-ui;margin:2rem;color:#172033}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}figure{{margin:0}}img{{width:100%;image-rendering:pixelated}}table{{border-collapse:collapse}}td,th{{padding:.5rem;border:1px solid #9aa7b8;text-align:right}}td:first-child,th:first-child{{text-align:left}}</style></head><body><h1>Zelda overlapping 3×3 sequential-encoding checkpoint</h1><p>Status: <b>{data['status']}</b></p>{image_html}<h2>Formula</h2><table><tr><th>Quantity</th><th>Value</th></tr><tr><td>Placement variables</td><td>{formula.get('placement_variables')}</td></tr><tr><td>Auxiliary variables</td><td>{formula.get('auxiliary_variables')}</td></tr><tr><td>Total variables</td><td>{formula.get('total_variables')}</td></tr><tr><td>At-least-one clauses</td><td>{formula.get('at_least_one_clauses')}</td></tr><tr><td>Sequential at-most-one clauses</td><td>{formula.get('sequential_at_most_one_clauses')}</td></tr><tr><td>Compatibility/support clauses</td><td>{formula.get('compatibility_support_clauses')}</td></tr><tr><td>Total clauses</td><td>{formula.get('total_clauses')}</td></tr></table><h2>Result</h2><pre>{json.dumps(result, indent=2)}</pre><h2>Four fidelity measurements</h2><table>{metric_rows}</table><h2>Timings</h2><pre>{json.dumps(timings, indent=2)}</pre><p><a href=context-seed-0.json>Raw JSON</a> · <a href=context-seed-0-timing.log>Timing log</a></p></body></html>""", encoding="utf-8")


def finalize_timeout():
    data = json.loads(RAW.read_text(encoding="utf-8"))
    data["status"] = "timeout"
    data["timings_seconds"]["solver_solve_lower_bound"] = 180.0 - 43.780992
    data["timings_seconds"]["total_wall_watchdog"] = 180.0
    data["result"].update({
        "status": "TIMEOUT", "conflicts": None, "decisions": None,
        "observer_backtracks": None, "output_image": None,
    })
    data["total_wall_seconds_so_far"] = 180.0
    RAW.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write("[180.000000s] external watchdog timeout; solver.solve() did not return\n")
        handle.flush()
    write_checkpoint(data)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize-timeout", action="store_true")
    args = parser.parse_args(argv)
    if args.finalize_timeout:
        finalize_timeout()
        return
    probe = Probe()
    probe.line("Zelda overlapping-3x3 sequential probe: seed=0 context lexical 20x20")
    source_grid, tile_rgba = probe.timed("source_loading", "source tile loading", tile_source)
    patterns, occurrences = probe.timed(
        "wrapped_pattern_extraction", "wrapped 3x3 pattern extraction",
        lambda: extract_pattern_occurrence_grid(source_grid, 3, extraction="periodic"),
    )
    allowed = probe.timed("compatibility", "overlap compatibility construction", lambda: build_compatibility(patterns))
    clause_counts = {}

    def timing_hook(event, stage, cnf):
        if event == "start":
            clause_counts[stage] = (len(cnf.clauses), time.perf_counter())
            probe.line(f"CNF {stage} start")
        else:
            before, started = clause_counts[stage]
            clause_counts[stage] = len(cnf.clauses) - before
            probe.timings[f"cnf_{stage}"] = time.perf_counter() - started
            probe.line(f"CNF {stage} complete: {probe.timings[f'cnf_{stage}']:.6f}s; added {clause_counts[stage]} clauses")

    cnf = probe.timed(
        "total_cnf_construction", "total sequential CNF construction",
        lambda: patterns_to_cnf(
            patterns, allowed, WIDTH, HEIGHT,
            adjacency_encoding="support", exactly_one_encoding="sequential",
            timing_hook=timing_hook,
        ),
    )
    placement_variables = len(cnf.name_map)
    formula = {
        "patterns": len(patterns), "output_cells": WIDTH * HEIGHT,
        "placement_variables": placement_variables,
        "auxiliary_variables": cnf.num_vars - placement_variables,
        "total_variables": cnf.num_vars,
        "at_least_one_clauses": WIDTH * HEIGHT,
        "sequential_at_most_one_clauses": clause_counts["exactly_one"] - WIDTH * HEIGHT,
        "compatibility_support_clauses": clause_counts["compatibility"],
        "total_clauses": len(cnf.clauses),
    }
    probe.data["formula"] = formula
    for key, value in formula.items(): probe.line(f"{key}: {value}")
    probe.save()

    from pysat.solvers import Cadical195
    solver = probe.timed("cadical_bootstrap", "CaDiCaL bootstrap", lambda: Cadical195(bootstrap_with=cnf.clauses, use_timer=True))
    try:
        def make_mapping():
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

        mapping = probe.timed("mapping_construction", "mapping construction/validation", make_mapping)

        def attach_observer():
            observer = DomainObserver(mapping, lambda event: None, heuristic="context", seed=0, selection="lexical")
            solver.connect_propagator(observer)
            return observer

        observer = probe.timed("observer_attach", "DomainObserver construction/connection", attach_observer)
        if len(observer.var_info) != placement_variables or any(
            variable not in cnf.name_map for variable in observer.var_info
        ):
            raise RuntimeError("auxiliary variable was mapped as a placement")

        def register():
            for placement in mapping.placements:
                solver.observe(placement.var)

        probe.timed("observe_registration", "placement observe() registration", register)
        probe.data["result"]["solve_entered"] = True
        probe.save()
        probe.line("solver.solve() start")
        started = time.perf_counter()
        sat = solver.solve()
        probe.timings["solver_solve"] = time.perf_counter() - started
        probe.line(f"solver.solve() complete: {probe.timings['solver_solve']:.6f}s")
        stats = solver.accum_stats()
        probe.data["result"].update({
            "status": "SAT" if sat else "UNSAT", "conflicts": stats.get("conflicts", 0),
            "decisions": stats.get("decisions", 0), "observer_backtracks": observer.backtrack_events,
        })
        if sat:
            model = solver.get_model()
            positive = {literal for literal in model if literal > 0}
            selected = {(x, y): pattern_id for variable, (x, y, pattern_id) in cnf.name_map.items() if variable in positive}
            if len(selected) != WIDTH * HEIGHT:
                raise RuntimeError("model does not select exactly one placement per cell")
            pattern_grid = tuple(tuple(selected[(x, y)] for x in range(WIDTH)) for y in range(HEIGHT))
            verify_semantics(pattern_grid, allowed)
            decoded = decode_patterns(pattern_grid, {pattern.id: pattern for pattern in patterns})
            reconstructed_source = tuple(tuple(row) for row in source_grid)
            # Wrapped occurrences reconstruct the source tile at each pattern origin.
            if tuple(tuple(patterns[occurrences[y][x]].rows[0][0] for x in range(len(source_grid[0]))) for y in range(len(source_grid))) != reconstructed_source:
                raise RuntimeError("source occurrence-grid reconstruction failed")
            metrics = {
                "pattern_frequency_kl": kl(oriented_distribution(pattern_grid), oriented_distribution(occurrences)),
                "pattern_edge_frequency_kl": kl(oriented_distribution(pattern_grid, True), oriented_distribution(occurrences, True)),
                "decoded_tile_frequency_kl": kl(oriented_distribution(decoded), oriented_distribution(reconstructed_source)),
                "decoded_tile_edge_frequency_kl": kl(oriented_distribution(decoded, True), oriented_distribution(reconstructed_source, True)),
            }
            probe.data["metrics"] = metrics
            render(decoded, tile_rgba)
            import hashlib
            probe.data["result"].update({
                "hard_constraints_verified": True,
                "decoded_dimensions_tiles": [len(decoded[0]), len(decoded)],
                "output_image": str(IMAGE.relative_to(ROOT)),
                "output_sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
            })
        probe.record_memory("solve/decode")
        probe.finish("completed")
    finally:
        solver.disconnect_propagator()
        solver.delete()
    write_checkpoint(probe.data)


if __name__ == "__main__":
    main()
