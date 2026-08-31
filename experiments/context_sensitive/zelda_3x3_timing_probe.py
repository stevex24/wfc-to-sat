#!/usr/bin/env python3
"""Safely stage the unchanged Zelda overlapping-3x3 SAT construction."""

from __future__ import annotations

import json
from pathlib import Path
import resource
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.zelda_experiment import SOURCE, tile_source
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.context_frequency import ContextFrequencies
from wfc_to_sat.patterns import extract_pattern_occurrence_grid


OUT = ROOT / "context-sensitive-results/detailed-comparison/zelda-3x3"
LOG = OUT / "zelda-3x3-context-seed-0-timing.log"
RAW = OUT / "zelda-3x3-context-seed-0.json"
CHECKPOINT = OUT / "index.html"
OUTPUT_WIDTH = 20
OUTPUT_HEIGHT = 20
MAX_SAFE_CLAUSES = 10_000_000


class Probe:
    def __init__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.timings = {}
        self.values = {}
        self.file = LOG.open("w", encoding="utf-8", buffering=1)

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
        return value

    def record(self, name, value):
        self.values[name] = value
        self.line(f"{name}: {value}")

    def save(self, status):
        total = time.perf_counter() - self.started
        payload = {
            "configuration": {
                "source": str(SOURCE.relative_to(ROOT)),
                "pattern_size": 3,
                "source_extraction": "periodic (wrap both axes)",
                "output": "20x20 placement grid",
                "output_boundary": "finite/nonperiodic",
                "seed": 0, "heuristic": "context", "selection": "lexical",
                "solver": "PySAT Cadical195 + DomainObserver",
                "encoding": "unchanged pairwise exactly-one + support compatibility",
            },
            "status": status,
            "timings_seconds": {**self.timings, "total_wall": total},
            "formula": self.values,
            "solver_result": None,
            "conflicts": None, "decisions": None,
            "observer_backtracks": None, "output_image": None,
        }
        RAW.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.line(f"status: {status}")
        self.line(f"total wall-clock: {total:.6f}s")
        self.line(f"raw_json: {RAW.relative_to(ROOT)}")
        self.file.close()
        return payload


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def write_checkpoint(payload):
    source_copy = OUT / "source.png"
    shutil.copyfile(SOURCE, source_copy)
    formula = payload["formula"]
    timings = payload["timings_seconds"]
    CHECKPOINT.write_text(f"""<!doctype html><html><head><meta charset=utf-8><title>Zelda 3x3 safety probe</title>
<style>body{{font:16px/1.5 system-ui;margin:2rem;max-width:1100px;color:#172033}}img{{max-width:100%;image-rendering:pixelated}}table{{border-collapse:collapse}}td,th{{border:1px solid #9aa7b8;padding:.5rem;text-align:right}}td:first-child,th:first-child{{text-align:left}}.stop{{padding:1rem;border-left:6px solid #b42318;background:#fff0ed}}</style></head><body>
<h1>Zelda overlapping 3×3 — Stage 1 safety checkpoint</h1><p>Seed 0 · Context · lexical · 20×20 placements · periodic source extraction · finite output boundary</p>
<img src=source.png alt='Source Zelda map'><p class=stop><b>Stopped before CNF allocation and solve.</b> The unchanged pairwise exactly-one representation would require {formula['total_clauses']:,} clauses. No SAT result or generated output exists.</p>
<table><tr><th>Quantity</th><th>Value</th></tr>
<tr><td>Extracted patterns</td><td>{formula['pattern_count']:,}</td></tr><tr><td>SAT variables</td><td>{formula['sat_variables']:,}</td></tr><tr><td>Exactly-one clauses</td><td>{formula['exactly_one_clauses']:,}</td></tr><tr><td>Compatibility/support clauses</td><td>{formula['compatibility_support_clauses']:,}</td></tr><tr><td>Total clauses</td><td>{formula['total_clauses']:,}</td></tr><tr><td>Conservative Python clause-container lower bound</td><td>{formula['clause_container_lower_bound_gib']:.1f} GiB</td></tr></table>
<h2>Measured preprocessing</h2><table><tr><th>Stage</th><th>Seconds</th></tr><tr><td>Source tile loading</td><td>{timings['source_tile_loading']:.6f}</td></tr><tr><td>Wrapped 3×3 extraction</td><td>{timings['pattern_extraction']:.6f}</td></tr><tr><td>Context-frequency construction</td><td>{timings['context_frequency']:.6f}</td></tr><tr><td>Compatibility construction</td><td>{timings['compatibility']:.6f}</td></tr><tr><td>Total wall</td><td>{timings['total_wall']:.6f}</td></tr></table>
<p>Unmeasured because of the safety stop: SAT-variable materialization, clause construction, CaDiCaL bootstrap, observer attachment/registration, and SAT search.</p><p><a href='zelda-3x3-context-seed-0.json'>Raw JSON</a> · <a href='zelda-3x3-context-seed-0-timing.log'>Timing log</a></p>
</body></html>""", encoding="utf-8")


def main():
    probe = Probe()
    probe.line("Zelda overlapping-3x3 Stage 1 probe: seed=0 heuristic=context selection=lexical output=20x20")
    source_grid, _rgba = probe.timed("source_tile_loading", "source tile loading", tile_source)
    patterns, occurrences = probe.timed(
        "pattern_extraction", "periodic wrapped 3x3 pattern extraction",
        lambda: extract_pattern_occurrence_grid(source_grid, 3, extraction="periodic"),
    )
    contexts = probe.timed(
        "context_frequency", "context-frequency construction",
        lambda: ContextFrequencies(occurrences),
    )
    allowed = probe.timed(
        "compatibility", "overlap compatibility construction",
        lambda: build_compatibility(patterns),
    )
    del contexts

    pattern_count = len(patterns)
    cells = OUTPUT_WIDTH * OUTPUT_HEIGHT
    output_edges = OUTPUT_HEIGHT * (OUTPUT_WIDTH - 1) + OUTPUT_WIDTH * (OUTPUT_HEIGHT - 1)
    variables = cells * pattern_count
    at_most_one = cells * pattern_count * (pattern_count - 1) // 2
    exactly_one = cells + at_most_one
    compatibility_support = output_edges * pattern_count
    total_clauses = exactly_one + compatibility_support
    child_list_bytes = sys.getsizeof([0, 0])
    pointer_bytes = sys.getsizeof([None]) - sys.getsizeof([])
    lower_bound = total_clauses * child_list_bytes + total_clauses * pointer_bytes

    probe.record("pattern_count", pattern_count)
    probe.record("source_pattern_occurrences", sum(map(len, occurrences)))
    probe.record("compatibility_right_links", sum(map(len, allowed["right"].values())))
    probe.record("compatibility_down_links", sum(map(len, allowed["down"].values())))
    probe.record("output_cells", cells)
    probe.record("output_adjacency_edges", output_edges)
    probe.record("sat_variables", variables)
    probe.record("at_least_one_clauses", cells)
    probe.record("pairwise_at_most_one_clauses", at_most_one)
    probe.record("exactly_one_clauses", exactly_one)
    probe.record("compatibility_support_clauses", compatibility_support)
    probe.record("total_clauses", total_clauses)
    probe.record("clause_container_lower_bound_bytes", lower_bound)
    probe.record("clause_container_lower_bound_gib", lower_bound / 1024 ** 3)
    probe.record("measured_peak_rss_bytes", peak_rss_bytes())
    probe.record("safety_clause_limit", MAX_SAFE_CLAUSES)

    if total_clauses > MAX_SAFE_CLAUSES:
        probe.line("SAFETY STOP before SAT variable/CNF allocation: unchanged formula exceeds clause limit")
        probe.timings.update({
            "sat_variable_allocation": None,
            "exactly_one_construction": None,
            "compatibility_clause_construction": None,
            "total_cnf_construction": None,
            "cadical_bootstrap": None,
            "observer_attach": None,
            "observe_registration": None,
            "solver_solve": None,
        })
        payload = probe.save("blocked_before_cnf_allocation")
        write_checkpoint(payload)
        return 2
    raise RuntimeError("safety expectation changed; review before allowing CNF construction")


if __name__ == "__main__":
    raise SystemExit(main())
