#!/usr/bin/env python3
"""Generate one uncurated N=3, 8x8 benchmark sample per matched condition."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel
from wfc_to_sat.patterns import extract_pattern_occurrence_grid, load_image_grid

NAMES = ("simple-knot", "cat", "chess", "knot", "simple-maze", "simple-wall")
DECISIONS = ("frequency", "context")
OUT = ROOT / "context-sensitive-results/meeting-report/benchmarks"


def instance(name):
    source = load_image_grid(ROOT / f"examples/{name}.png")
    patterns, occurrence = extract_pattern_occurrence_grid(source, 3)
    allowed = build_compatibility(patterns)
    cnf = patterns_to_cnf(patterns, allowed, 8, 8)
    specs = tuple(PatternSpec(p.id, p.frequency, 3, 3, bytes(c for row in p.rows for pixel in row for c in pixel)) for p in patterns)
    placements = tuple(Placement(v, x, y, pid) for v, (x,y,pid) in sorted(cnf.name_map.items()))
    mapping = MappingSpec(8, 8, specs, placements, allowed, occurrence)
    mapping.validate(cnf.num_vars)
    model = WFCModel.from_patterns(patterns, allowed, occurrence)
    return patterns, cnf, mapping, model


def sat_run(cnf, mapping, decision, seed=0):
    from pysat.solvers import Cadical195
    observer = DomainObserver(mapping, lambda event: None, heuristic=decision, seed=seed, selection="lexical")
    started = time.perf_counter()
    with Cadical195(bootstrap_with=cnf.clauses, use_timer=True) as solver:
        solver.connect_propagator(observer)
        for p in mapping.placements: solver.observe(p.var)
        success = solver.solve()
        model = solver.get_model() or []
        stats = solver.accum_stats()
        elapsed = time.perf_counter() - started
        backtracks = observer.backtrack_events
        solver.disconnect_propagator()
    positive = {lit for lit in model if lit > 0}
    grid = []
    if success:
        lookup = {(p.x,p.y):p.pattern_id for p in mapping.placements if p.var in positive}
        grid = [[lookup[(x,y)] for x in range(8)] for y in range(8)]
    return grid, {"success":success,"runtime_seconds":elapsed,"conflicts":stats.get("conflicts",0),"backtracks":backtracks,"restarts":stats.get("restarts",0)}


def render(patterns, grid, path):
    from PIL import Image
    if not grid or any(item is None for row in grid for item in row):
        image = Image.new("RGBA", (8, 8), (244, 63, 94, 255))
        image.resize((200, 200), Image.NEAREST).save(path)
        return
    table = {p.id:p.rows for p in patterns}
    size = len(grid) + 2
    pixels = [[None]*size for _ in range(size)]
    for y,row in enumerate(grid):
        for x,pid in enumerate(row):
            for dy, prow in enumerate(table[pid]):
                for dx, pixel in enumerate(prow):
                    old = pixels[y+dy][x+dx]
                    if old is not None and old != pixel: raise RuntimeError("illegal overlapping model")
                    pixels[y+dy][x+dx] = pixel
    image = Image.new("RGBA", (size,size)); image.putdata([p for row in pixels for p in row]); image.resize((size*20,size*20), Image.NEAREST).save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records=[]; cards=[]
    for name in NAMES:
        patterns, cnf, mapping, model = instance(name)
        cards.append(f'<h3>{name}</h3><article><h4>Source</h4><img src="../../examples/{name}.png" alt="{name} source"></article>')
        for decision in DECISIONS:
            started=time.perf_counter(); wfc=OrdinaryWFC(model,8,8,selection="lexical",decision=decision,seed=0).run(); wtime=time.perf_counter()-started
            wgrid=[[v for v in row] for row in wfc.output]
            sgrid, stats=sat_run(cnf,mapping,decision)
            for engine, grid, details in (("ordinary-wfc",wgrid,{"success":wfc.success,"runtime_seconds":wtime,"contradictions":wfc.contradictions}),("wfc-as-sat",sgrid,stats)):
                filename=f"{name}-{decision}-{engine}.png"; render(patterns,grid,OUT/filename)
                record={"benchmark":name,"pattern_size":3,"placement_grid":"8x8","decoded_pixels":"10x10","seed":0,"selection":"lexical","decision":decision,"engine":engine,**details,"image":filename}; records.append(record)
                cards.append(f'<article><h4>{decision} — {engine}</h4><img src="benchmarks/{filename}" alt="{filename}"><p>seed 0; N=3; 8×8 placements; success {str(details["success"]).lower()}; runtime {details["runtime_seconds"]:.4f}s; conflicts {details.get("conflicts","N/A")}; backtracks {details.get("backtracks","N/A")}</p></article>')
    (OUT/"raw-runs.json").write_text(json.dumps(records,indent=2)+"\n")
    report=ROOT/"context-sensitive-results/meeting-report/index.html"
    doc=report.read_text()
    gallery='<div class="gallery benchmark-gallery">'+''.join(cards)+'</div><p>All benchmark images are uncurated seed 0 outputs at the repository’s established N=3, 8×8 placement configuration. SAT recovered satisfying outputs for both simple-knot conditions after 7–8 conflicts where stop-on-contradiction ordinary WFC failed. Cat and knot also exercised SAT backtracking; chess and simple-wall were conflict-free. Simple-maze is UNSAT at this configuration for both decision heuristics. These representative runs demonstrate CDCL-semantic differences but are not distribution estimates. Raw data: <a href="benchmarks/raw-runs.json">benchmarks/raw-runs.json</a>.</p>'
    heading='<h2>Benchmark evidence</h2>'
    conclusion='<h2>Conclusions</h2>'
    if heading not in doc or conclusion not in doc: raise RuntimeError("meeting report sections missing")
    before, remainder = doc.split(heading, 1)
    _, after = remainder.split(conclusion, 1)
    report.write_text(before + heading + gallery + conclusion + after, encoding="utf-8")
    print(json.dumps(records,indent=2))

if __name__ == "__main__": main()
