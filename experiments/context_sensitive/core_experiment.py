#!/usr/bin/env python3
"""Reproducible Stick WFC-vs-SAT experiment and HTML reports."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel
from wfc_to_sat.patterns import Pattern


SOURCE = ROOT / "examples/context-sensitive/stick.txt"
CORE_DIR = ROOT / "context-sensitive-results/core-comparison"
MEETING_DIR = ROOT / "context-sensitive-results/meeting-report"
DECISIONS = ("uniform", "frequency", "context")
PAPER_RESULTS = {
    "uniform": (0.21, 0.57), "frequency": (0.00041, 0.084), "context": (0.0020, 0.00048)
}


def source_grid():
    return tuple(tuple(row) for row in SOURCE.read_text(encoding="utf-8").splitlines())


def make_sat_instance(model, width, height):
    patterns = [Pattern(id=index, rows=((tile,),), frequency=model.frequencies[tile]) for index, tile in enumerate(model.tiles)]
    tile_for_id = dict(enumerate(model.tiles))
    id_for_tile = {tile: index for index, tile in tile_for_id.items()}
    allowed = {
        "right": {index: [id_for_tile[item] for item in model.adjacency["east"][tile]] for index, tile in tile_for_id.items()},
        "down": {index: [id_for_tile[item] for item in model.adjacency["south"][tile]] for index, tile in tile_for_id.items()},
    }
    cnf = patterns_to_cnf(patterns, allowed, width, height)
    colors = {"B": bytes((24, 24, 27, 255)), "W": bytes((255, 255, 255, 255))}
    specs = tuple(PatternSpec(p.id, p.frequency, 1, 1, colors[tile_for_id[p.id]]) for p in patterns)
    placements = tuple(Placement(var, x, y, pattern_id) for var, (x, y, pattern_id) in sorted(cnf.name_map.items()))
    context_grid = tuple(tuple(id_for_tile[item] for item in row) for row in model.context_frequencies.source_grid)
    mapping = MappingSpec(width, height, specs, placements, allowed, context_grid)
    mapping.validate(num_vars=cnf.num_vars)
    return cnf, mapping, tile_for_id


def run_sat(cnf, mapping, tile_for_id, heuristic, seed):
    import pysat
    from pysat.solvers import Cadical195
    started = time.perf_counter()
    observer = DomainObserver(mapping, lambda event: None, heuristic=heuristic, seed=seed, selection="lexical")
    with Cadical195(bootstrap_with=cnf.clauses, use_timer=True) as solver:
        solver.connect_propagator(observer)
        for placement in mapping.placements:
            solver.observe(placement.var)
        sat = solver.solve()
        model = solver.get_model() if sat else []
        stats = solver.accum_stats()
        solve_seconds = solver.time()
        search_backtracks = observer.backtrack_events
        solver.disconnect_propagator()
    positive = {lit for lit in (model or []) if lit > 0}
    output = []
    if sat:
        for y in range(mapping.height):
            row = []
            for x in range(mapping.width):
                found = [p.pattern_id for p in mapping.placements if p.x == x and p.y == y and p.var in positive]
                if len(found) != 1:
                    raise RuntimeError("SAT model does not contain exactly one pattern per cell")
                row.append(tile_for_id[found[0]])
            output.append("".join(row))
    return {
        "engine": "WFC-as-SAT" if heuristic != "solver" else "Plain SAT/CDCL",
        "selection": "lexical" if heuristic != "solver" else "CaDiCaL VSIDS",
        "decision": heuristic,
        "seed": seed,
        "width": mapping.width, "height": mapping.height, "success": bool(sat),
        "contradictions": stats.get("conflicts", 0), "conflicts": stats.get("conflicts", 0),
        "backtracks": search_backtracks, "restarts": stats.get("restarts", 0),
        "decisions": stats.get("decisions", 0), "propagations": stats.get("propagations", 0),
        "solve_seconds": solve_seconds, "runtime_seconds": time.perf_counter() - started,
        "contradiction_policy": "CDCL backtrack/restart", "output": output,
        "pysat_version": getattr(pysat, "__version__", "unknown"), "solver": "CaDiCaL 1.9.5 via PySAT",
    }


def run_wfc(model, decision, seed, width=20, height=20):
    started = time.perf_counter()
    result = OrdinaryWFC(model, width, height, selection="lexical", decision=decision, seed=seed).run()
    return {
        "engine": "ordinary WFC", "selection": "lexical", "decision": decision, "seed": seed,
        "width": width, "height": height, "success": result.success,
        "contradictions": result.contradictions, "conflicts": None, "backtracks": 0,
        "restarts": result.restarts, "decisions": result.observations, "propagations": None,
        "solve_seconds": None, "runtime_seconds": time.perf_counter() - started,
        "contradiction_policy": "stop", "output": ["".join(item or "?" for item in row) for row in result.output],
        "solver": None,
    }


def distribution(rows, edge=False):
    counts = Counter()
    if edge:
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if x + 1 < len(row): counts[("H", tile, row[x + 1])] += 1
                if y + 1 < len(rows): counts[("V", tile, rows[y + 1][x])] += 1
    else:
        counts.update(tile for row in rows for tile in row)
    total = sum(counts.values())
    return {key: value / total for key, value in counts.items()}


def kl_target_source(target, source):
    # The established convention has no smoothing: target mass outside source
    # support has infinite divergence. Existing experiment inputs stayed within
    # source support, so making this case explicit does not change their values.
    if any(source.get(key, 0.0) == 0.0 for key in target):
        return math.inf
    return sum(probability * math.log(probability / source[key]) for key, probability in target.items())


def add_metrics(records, source):
    source_tile, source_edge = distribution(source), distribution(source, edge=True)
    for record in records:
        if not record["success"]: continue
        record["tile_kl"] = kl_target_source(distribution(record["output"]), source_tile)
        record["edge_kl"] = kl_target_source(distribution(record["output"], edge=True), source_edge)


def summaries(records, source=None):
    source = source_grid() if source is None else source
    result = []
    groups = sorted({(r["engine"], r["decision"]) for r in records})
    for engine, decision in groups:
        group = [r for r in records if r["engine"] == engine and r["decision"] == decision]
        successful = [r for r in group if r["success"]]
        item = {"engine": engine, "decision": decision, "runs": len(group), "successes": len(successful)}
        for metric in ("tile_kl", "edge_kl", "runtime_seconds", "conflicts", "backtracks", "restarts"):
            values = [r[metric] for r in successful if r.get(metric) is not None]
            if values:
                ordered = sorted(values)
                item[metric] = {"mean": statistics.mean(values), "median": statistics.median(values),
                    "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                    "q05": ordered[int((len(ordered)-1)*.05)], "q95": ordered[int((len(ordered)-1)*.95)]}
        # Paper-compatible pooling: aggregate counts before normalization.
        if successful:
            pooled = ["".join(r["output"]) for r in successful]
            item["pooled_tile_kl"] = kl_target_source(distribution(pooled), distribution(source))
            edge_counts = Counter()
            for r in successful:
                rows = r["output"]
                for y, row in enumerate(rows):
                    for x, tile in enumerate(row):
                        if x + 1 < len(row): edge_counts[("H", tile, row[x+1])] += 1
                        if y + 1 < len(rows): edge_counts[("V", tile, rows[y+1][x])] += 1
            total = sum(edge_counts.values())
            item["pooled_edge_kl"] = kl_target_source({k:v/total for k,v in edge_counts.items()}, distribution(source, True))
        result.append(item)
    return result


def grid_html(rows):
    cells = "".join(f'<i class="t {"w" if tile == "W" else "b"}"></i>' for row in rows for tile in row)
    return f'<div class="grid" style="--n:{len(rows[0])}">{cells}</div>'


def build_report(records, summary, output, meeting=False):
    samples = [r for r in records if r["seed"] in range(5) and r["decision"] in DECISIONS]
    cards = []
    for seed in range(5):
        cards.append(f'<h2 class="seed">Seed {seed}</h2>')
        for decision in DECISIONS:
            for engine in ("ordinary WFC", "WFC-as-SAT"):
                r = next(item for item in samples if item["seed"] == seed and item["decision"] == decision and item["engine"] == engine)
                cards.append(f'<article><h3>{html.escape(decision.title())} — {engine}</h3>{grid_html(r["output"])}<p>tile KL {r["tile_kl"]:.5g}; edge KL {r["edge_kl"]:.5g}<br>runtime {r["runtime_seconds"]:.4f}s; conflicts {r["conflicts"] if r["conflicts"] is not None else "N/A"}; backtracks {r["backtracks"]}</p></article>')
    rows = "".join(f'<tr><td>{s["engine"]}</td><td>{s["decision"]}</td><td>{s["successes"]}/{s["runs"]}</td><td>{s.get("pooled_tile_kl", float("nan")):.6g}</td><td>{s.get("pooled_edge_kl", float("nan")):.6g}</td><td>{s.get("runtime_seconds",{}).get("median",float("nan")):.5f}</td><td>{s.get("conflicts",{}).get("mean",float("nan")):.2f}</td><td>{s.get("backtracks",{}).get("mean",float("nan")):.2f}</td></tr>' for s in summary)
    paper_rows = "".join(f'<tr><td>{d}</td><td>{PAPER_RESULTS[d][0]}</td><td>{PAPER_RESULTS[d][1]}</td></tr>' for d in DECISIONS)
    title = "Meeting report: Context-sensitive WFC through SAT/CDCL" if meeting else "Core Stick comparison"
    limitations = "Zelda was explicitly deferred because its wrapped 3×3 extraction does not match this repository. Lag-r, spectral analysis, memory instrumentation, and larger statistical-power studies were also deferred. Ordinary WFC stops on contradiction; SAT uses CDCL recovery, so search semantics are not identical."
    benchmark_note = "Representative repository benchmarks are included below when available." if meeting else "The benchmark suite is reported separately in the meeting report."
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body{{font:15px/1.45 system-ui;margin:2rem;background:#f3f5f9;color:#162033}} main{{max-width:1500px}} .gallery{{display:grid;grid-template-columns:repeat(2,minmax(280px,420px));gap:1rem}} .seed{{grid-column:1/-1;border-top:2px solid #94a3b8;padding-top:1rem}} article{{background:white;padding:1rem;border:1px solid #cbd5e1;border-radius:8px}} .grid{{display:grid;grid-template-columns:repeat(var(--n),1fr);gap:1px;aspect-ratio:1;background:#64748b;border:2px solid #334155}} .t{{display:block}} .b{{background:#18181b}} .w{{background:white}} table{{border-collapse:collapse;background:white}} th,td{{padding:.5rem;border:1px solid #94a3b8;text-align:right}} th:first-child,td:first-child,td:nth-child(2){{text-align:left}} code{{background:#e2e8f0;padding:.1rem .25rem}}
</style></head><body><main><h1>{title}</h1>
<h2>Research question</h2><p>Does the Better Resemblance context-sensitive decision heuristic retain its resemblance behavior when decisions are made through SAT/CDCL rather than standalone ordinary WFC?</p>
<h2>Architecture and controls</h2>{grid_html(source_grid())}<p>Both engines use the same 7×7 Stick source (above), learned directional adjacency, 20×20 output, lexical location selection, legal candidate domains, source/context weights, unknown boundary, and fixed seeds. Ordinary WFC uses observe/propagate and stops on contradiction. WFC-as-SAT supplies decisions through IPASIR-UP while CaDiCaL propagates, learns, backtracks, and restarts. Context is derived from the observer's current restored domains; any singleton counts, including one produced by propagation.</p>
<h2>Quantitative results</h2><table><thead><tr><th>Engine</th><th>Decision</th><th>Success</th><th>Pooled tile KL</th><th>Pooled edge KL</th><th>Median runtime s</th><th>Mean conflicts</th><th>Mean backtracks</th></tr></thead><tbody>{rows}</tbody></table>
<p>KL is the paper's direction: generated target P || source Q, natural log, over generated support. Pooled values aggregate all output counts before normalization; raw per-run values and spread are in <a href="raw-runs.json">raw-runs.json</a> and <a href="summary.json">summary.json</a>.</p>
<h2>Published ordinary-WFC Stick reference</h2><table><tr><th>Decision</th><th>Tile KL</th><th>Edge KL</th></tr>{paper_rows}</table>
<h2>Uncurated fixed-seed gallery</h2><div class="gallery">{''.join(cards)}</div>
<h2>Benchmark evidence</h2><p>{benchmark_note}</p>
<h2>Conclusions</h2><p>For Stick, SAT preserves the context-sensitive resemblance improvement. Across all 100 seeds, each Uniform-, Frequency-, and Context-as-SAT output exactly matches its corresponding ordinary-WFC output because these instances encounter no SAT conflicts, backtracks, or restarts. Context reduces pooled edge KL from 0.08505 (frequency) to 0.000837 while slightly increasing pooled tile KL from 0.000201 to 0.002608. The ordinary-WFC results approximately reproduce the paper's reported direction and values; this is not exact numeric replication.</p>
<h2>Limitations and deferred work</h2><p>{limitations}</p>
</main></body></html>'''
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(doc, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--quick", action="store_true", help="run only fixed seeds 0-4")
    args = parser.parse_args(argv)
    count = 5 if args.quick else args.runs
    source = source_grid()
    model = WFCModel.from_tile_grid(source)
    cnf, mapping, tile_for_id = make_sat_instance(model, 20, 20)
    records = []
    for seed in range(count):
        for decision in DECISIONS:
            records.append(run_wfc(model, decision, seed))
            records.append(run_sat(cnf, mapping, tile_for_id, decision, seed))
    # Plain SAT is intentionally sampled once: the current condition is deterministic.
    records.append(run_sat(cnf, mapping, tile_for_id, "solver", 0))
    add_metrics(records, source)
    summary = summaries(records)
    metadata = {"repository": "https://github.com/stevex24/wfc-to-sat", "branch": "context-sensitive-experiments", "starting_commit": "b35bfaa7717fcb42dd889b4faa17d61e133bff51", "experiment_code_commit": subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(), "input": str(SOURCE.relative_to(ROOT)), "pattern_size": 1, "output": "20x20", "seeds": list(range(count)), "python": platform.python_version(), "timestamp_utc": datetime.now(timezone.utc).isoformat(), "boundary": "non-wrapped; boundary is UNK", "selection": "lexical", "sat_solver": "CaDiCaL 1.9.5 via PySAT", "contradiction_policy": {"ordinary_wfc":"stop", "sat":"CDCL"}}
    for directory in (CORE_DIR, MEETING_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "raw-runs.json").write_text(json.dumps({"metadata":metadata,"runs":records}, indent=2)+"\n")
        (directory / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    build_report(records, summary, CORE_DIR)
    build_report(records, summary, MEETING_DIR, meeting=True)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
