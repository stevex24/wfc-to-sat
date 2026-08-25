#!/usr/bin/env python3
"""Analyze completed outputs with axis-specific lag-r pair frequencies."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.core_experiment import distribution, source_grid
from experiments.context_sensitive.lag_r_metrics import lag_kl, lag_pair_counts, normalized

OUT = ROOT / "context-sensitive-results/lag-r"
LAGS = (1, 2, 4, 8, 16, 32)
BENCHMARKS = ("simple-knot", "cat", "chess", "knot", "simple-wall", "simple-maze")
AXES = ("horizontal", "vertical")


def image_grid(path):
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels = list(image.getdata())
    return tuple(tuple(pixels[y * width + x] for x in range(width)) for y in range(height))


def completed_output_grid(path):
    """Read the established nearest-neighbor-rendered 10x10 benchmark artifact."""
    image = Image.open(path).convert("RGBA")
    if image.size != (200, 200):
        raise ValueError(f"unexpected completed output dimensions: {path}: {image.size}")
    return tuple(tuple(image.getpixel((x * 20 + 10, y * 20 + 10)) for x in range(10)) for y in range(10))


def available_lags(source, target):
    sw, sh = len(source[0]), len(source)
    tw, th = len(target[0]), len(target)
    return {"horizontal": [r for r in LAGS if r < min(sw, tw)],
            "vertical": [r for r in LAGS if r < min(sh, th)]}


def value_text(value):
    return "∞" if math.isinf(value) else f"{value:.6g}"


COLORS = {"frequency — ordinary WFC": "#2563eb", "frequency — WFC-as-SAT": "#f97316",
          "context — ordinary WFC": "#16a34a", "context — WFC-as-SAT": "#dc2626",
          "uniform — ordinary WFC": "#7c3aed", "uniform — WFC-as-SAT": "#0891b2"}


def svg_plot(series, axis, title):
    width, height, left, top, bottom = 650, 330, 58, 30, 48
    values = [p["kl"] for line in series for p in line[axis] if math.isfinite(p["kl"])]
    ymax = max(values + [1e-6]) * 1.08
    lags = sorted({p["lag"] for line in series for p in line[axis]})
    xpos = {r: left + i * (width-left-25) / max(1, len(lags)-1) for i, r in enumerate(lags)}
    def ypos(v): return top if math.isinf(v) else top + (height-top-bottom) * (1-v/ymax)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
             f'<rect width="100%" height="100%" fill="white"/><text x="{left}" y="18" font-size="14">{html.escape(title)}</text>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-20}" y2="{height-bottom}" stroke="#475569"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#475569"/>',
             f'<text x="5" y="{top+5}" font-size="11">{ymax:.3g}</text><text x="25" y="{height-bottom+4}" font-size="11">0</text>']
    for r in lags:
        parts.append(f'<text x="{xpos[r]}" y="{height-25}" text-anchor="middle" font-size="11">{r}</text>')
    for line in series:
        color = COLORS.get(line["label"], "#334155")
        pts = [(xpos[p["lag"]], ypos(p["kl"]), p["kl"]) for p in line[axis]]
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y,_ in pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y, value in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/><title>{html.escape(line["label"])}: {value_text(value)}</title>')
            if math.isinf(value): parts.append(f'<text x="{x:.1f}" y="{y+13:.1f}" text-anchor="middle" fill="{color}">∞</text>')
    y = height - 8
    for i, line in enumerate(series):
        x = left + i % 3 * 195
        yy = y - (len(series)-1-i)//3*16
        color = COLORS.get(line["label"], "#334155")
        parts.append(f'<line x1="{x}" y1="{yy-4}" x2="{x+14}" y2="{yy-4}" stroke="{color}" stroke-width="3"/><text x="{x+18}" y="{yy}" font-size="10">{html.escape(line["label"])}</text>')
    parts.append('</svg>')
    return "".join(parts)


def analyze_series(source, groups):
    result = []
    for label, grids in groups:
        lags = available_lags(source, grids[0])
        line = {"label": label, "sample_count": len(grids)}
        for axis in AXES:
            line[axis] = [{"lag": r, "kl": lag_kl(grids, source, r, axis)} for r in lags[axis]]
        result.append(line)
    return result


def table(series):
    rows = []
    for line in series:
        by_axis = {axis: {p["lag"]: p["kl"] for p in line[axis]} for axis in AXES}
        for lag in sorted(set(by_axis["horizontal"]) | set(by_axis["vertical"])):
            rows.append(f'<tr><td>{html.escape(line["label"])}</td><td>{line["sample_count"]}</td><td>{lag}</td><td>{value_text(by_axis["horizontal"].get(lag, math.nan))}</td><td>{value_text(by_axis["vertical"].get(lag, math.nan))}</td></tr>')
    return '<table><thead><tr><th>Condition</th><th>n</th><th>r</th><th>Horizontal KL</th><th>Vertical KL</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


INTERPRETATION = {
    "simple-knot": "Only SAT succeeded. Context is better than frequency at r=1 and r=2 horizontally and at r=2 vertically, but worse at vertical r=1 and at both axes for the longer r=4 and r=8 comparisons. The context advantage therefore does not persist uniformly.",
    "cat": "Context improves most horizontal and vertical values through r=8. CDCL changes the representative output substantially: context-as-SAT is best horizontally at every lag, but its vertical KL rises sharply at r=8, unlike ordinary context WFC. This nonlocal reversal is invisible in a pooled edge-KL number.",
    "chess": "Every condition is an exact lag-r match to the periodic source for every measurable lag. Lag-r adds no distinction on this deterministic representative case.",
    "knot": "The ranking depends on direction and distance. Ordinary context WFC is worse than frequency horizontally at r=1, while context-as-SAT is markedly better near-range on both axes. At r=8 neither context condition dominates both axes. The SAT/WFC separation after CDCL conflicts persists beyond adjacency.",
    "simple-wall": "All four representative outputs and curves coincide. KL grows more strongly with vertical distance than horizontal distance, but neither heuristic nor engine is distinguished in this conflict-free case.",
}


def main():
    started = time.perf_counter()
    core = json.loads((ROOT / "context-sensitive-results/core-comparison/raw-runs.json").read_text())
    stick_runs = [r for r in core["runs"] if r["success"] and r["decision"] in ("uniform", "frequency", "context") and r["engine"] in ("ordinary WFC", "WFC-as-SAT")]
    stick_groups = []
    for decision in ("uniform", "frequency", "context"):
        for engine in ("ordinary WFC", "WFC-as-SAT"):
            grids = [tuple(tuple(row) for row in r["output"]) for r in stick_runs if r["decision"] == decision and r["engine"] == engine]
            stick_groups.append((f"{decision} — {engine}", grids))
    stick = analyze_series(source_grid(), stick_groups)

    benchmark_raw = json.loads((ROOT / "context-sensitive-results/meeting-report/benchmarks/raw-runs.json").read_text())
    benchmark_sections, benchmark_data = [], {}
    for name in BENCHMARKS:
        records = [r for r in benchmark_raw if r["benchmark"] == name]
        successful = [r for r in records if r["success"]]
        if name == "simple-maze":
            benchmark_sections.append('<section><h2>simple-maze — established configuration UNSAT</h2><p>All four seed-0 conditions are UNSAT, so there is no generated grid and no lag-r measurement. Failed cases were not silently omitted.</p></section>')
            benchmark_data[name] = {"study_type": "representative single-seed", "status": "UNSAT", "series": []}
            continue
        source = image_grid(ROOT / f"examples/{name}.png")
        groups = []
        cards = [f'<article><h3>Source</h3><img src="../../examples/{name}.png" alt="{name} source"></article>']
        for record in successful:
            engine_label = "ordinary WFC" if record["engine"] == "ordinary-wfc" else "WFC-as-SAT"
            label = f'{record["decision"]} — {engine_label}'
            artifact = ROOT / "context-sensitive-results/meeting-report/benchmarks" / record["image"]
            groups.append((label, [completed_output_grid(artifact)]))
            cards.append(f'<article><h3>{html.escape(label)}</h3><img src="../meeting-report/benchmarks/{record["image"]}" alt="{html.escape(label)}"><p>seed 0; {record["conflicts"] if "conflicts" in record else "N/A"} conflicts; {record.get("backtracks", "N/A")} backtracks</p></article>')
        series = analyze_series(source, groups)
        failures = [r for r in records if not r["success"]]
        failure_note = '' if not failures else '<p class="warning">No lag values for failed ordinary-WFC cases: '+', '.join(r["decision"] for r in failures)+'. SAT recovered solutions after conflicts/backtracking.</p>'
        benchmark_sections.append(f'<section><h2>{name} — representative seed 0</h2><p>This is one representative example, not a distribution estimate. Metrics compare decoded RGBA tile pixels in the source with the completed 10×10 decoded output.</p>{failure_note}<div class="gallery">{"".join(cards)}</div><div class="plots">{svg_plot(series,"horizontal",name+" horizontal")}{svg_plot(series,"vertical",name+" vertical")}</div>{table(series)}<p><strong>Interpretation:</strong> {INTERPRETATION[name]}</p></section>')
        benchmark_data[name] = {"study_type": "representative single-seed", "seeds": [0], "series": series, "failed_conditions": [{k:r.get(k) for k in ("engine","decision","success","conflicts","backtracks")} for r in failures]}

    # Explicit correctness checks against facts established by the completed run.
    paired_equal = all(next(g for l,g in stick_groups if l == f"{d} — ordinary WFC") == next(g for l,g in stick_groups if l == f"{d} — WFC-as-SAT") for d in ("uniform","frequency","context"))
    source = source_grid(); h = lag_pair_counts(source,1,"horizontal"); v = lag_pair_counts(source,1,"vertical")
    combined = {("H",*k):v0 for k,v0 in h.items()}; combined.update({("V",*k):v0 for k,v0 in v.items()})
    r1_matches_edge = normalized(combined) == distribution(source, edge=True)
    elapsed = time.perf_counter() - started
    payload = {"metadata":{"generated_utc":datetime.now(timezone.utc).isoformat(),"lags_requested":list(LAGS),"kl":"generated P || source Q; natural log; no smoothing; generated mass outside source support is infinity","pairs":"ordered; axes separate; non-wrapped; valid in-bounds origins only","stick_study_type":"100-run pooled distribution study","stick_seeds":list(range(100)),"benchmark_study_type":"representative single-seed","benchmark_seeds":[0],"analysis_seconds":elapsed},"validation":{"stick_wfc_sat_outputs_identical":paired_equal,"lag1_combined_distribution_equals_existing_oriented_edge_distribution":r1_matches_edge},"stick":stick,"benchmarks":benchmark_data}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=True)+"\n")
    source_png = Image.new("RGBA", (70,70)); px = source_png.load()
    for y,row in enumerate(source_grid()):
        for x,tile in enumerate(row):
            color = (255,255,255,255) if tile == "W" else (24,24,27,255)
            for yy in range(y*10,(y+1)*10):
                for xx in range(x*10,(x+1)*10): px[xx,yy] = color
    source_png.save(OUT / "stick-source.png")
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><title>Lag-r spatial resemblance</title><style>body{{font:15px/1.5 system-ui;margin:2rem;background:#f1f5f9;color:#172033}}main{{max-width:1450px}}section{{margin:2.5rem 0}}.gallery{{display:flex;flex-wrap:wrap;gap:1rem}}article{{background:white;border:1px solid #cbd5e1;padding:.8rem;max-width:230px}}img{{image-rendering:pixelated;max-width:200px;max-height:200px}}.plots{{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:1rem}}svg,table{{background:white;border:1px solid #cbd5e1}}table{{border-collapse:collapse}}th,td{{padding:.35rem .55rem;border:1px solid #cbd5e1;text-align:right}}th:first-child,td:first-child{{text-align:left}}.warning{{color:#9f1239;font-weight:600}}code{{background:#e2e8f0;padding:.1rem .25rem}}</style></head><body><main><h1>Lag-r spatial resemblance experiment</h1><p><strong>Question:</strong> does context-sensitive resemblance persist beyond immediate adjacency? Ordered pairs are measured independently at horizontal and vertical displacement r. Only lags supported by both source and output are shown.</p><h2>Metric convention</h2><p>For each axis and lag, raw ordered-pair counts are pooled across outputs, then normalized within that axis/lag. KL is generated target P || source Q with natural logarithms, reusing the completed experiment implementation. There is no pseudocount or smoothing: generated mass on a source-zero pair yields ∞. Boundaries do not wrap and contribute no pair. Horizontal and vertical distributions are never pooled here.</p><section><h2>Stick — 100-run distribution study</h2><p>Seeds 0–99; 100 successful outputs per condition. The 7×7 source limits comparisons to r=1,2,4. All ordinary-WFC/SAT paired outputs were already known to be identical, and the lag curves match exactly as a correctness consequence—not a new engine result.</p><div class="gallery"><article><h3>Source</h3><img src="stick-source.png" alt="Stick source"></article></div><div class="plots">{svg_plot(stick,"horizontal","Stick horizontal")}{svg_plot(stick,"vertical","Stick vertical")}</div>{table(stick)}<p><strong>Interpretation:</strong> Context's vertical improvement persists beyond adjacency: KL is 0.00138, 0.0153, and 0.0178 at r=1,2,4 versus frequency's 0.1637, 0.1321, and 0.0503. The advantage narrows with distance but does not decay monotonically. Horizontally, context is much better at r=1, but every condition has ∞ KL at r=2 and r=4 because generated outputs contain pairs absent from the tiny source; the unsmoothed metric cannot rank them there. The large horizontal/vertical difference confirms the expected directional structure.</p></section>{''.join(benchmark_sections)}<section><h2>Validation and overall interpretation</h2><p>Lag-1 horizontal and vertical counts, after adding the existing H/V orientation tags and pooling, reproduce the completed oriented edge-frequency distribution exactly: <strong>{str(r1_matches_edge).lower()}</strong>. All 100 paired Stick WFC/SAT grids—and therefore every lag measurement—match: <strong>{str(paired_equal).lower()}</strong>.</p><p>Lag-r adds useful information beyond edge KL: it shows persistence of the Stick vertical advantage, exposes unsupported horizontal long-lag pairs, and reveals distance-dependent reversals in cat, knot, and simple-knot. The representative CDCL cases show nonlocal WFC/SAT differences, especially cat vertical r=8 and knot across several lags, but one seed cannot support distribution-level claims. Improvement is not generally a smooth decay and is strongly directional.</p><p>Read the exact values above rather than inferring from the lines. Infinite values are scientifically meaningful under the established unsmoothed support convention. Repository examples are seed-0 diagnostics only; differences there may expose nonlocal CDCL effects, but cannot establish a generator distribution.</p><h2>Limitations</h2><p>No extra generation was performed. Stick's small source prevents r≥8. Benchmark conclusions are representative examples, output/source sizes differ, RGBA decoded pixels are measured rather than pattern identities, and UNSAT/failed outputs have no fabricated metric. Lag-r captures two-point displacement structure but not higher-order or topological structure.</p><p>Analysis runtime: {elapsed:.3f} seconds. Machine-readable values: <a href="results.json">results.json</a>.</p></section></main></body></html>'''
    (OUT / "index.html").write_text(doc, encoding="utf-8")
    print(json.dumps({"output":str(OUT/"index.html"),"analysis_seconds":elapsed,"validation":payload["validation"]},indent=2))


if __name__ == "__main__":
    main()
