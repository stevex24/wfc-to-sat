#!/usr/bin/env python3
"""Run the matched von-Neumann versus Moore context experiment."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel
from wfc_to_sat.patterns import Pattern, extract_pattern_occurrence_grid, load_image_grid

OUT = ROOT / "context-sensitive-results/moore-context"
DECISIONS = ("frequency", "context", "context_moore")
LABELS = {"frequency":"Frequency", "context":"Context-4", "context_moore":"Context-8"}
BENCHMARKS = ("stick", "letter-z", "cat", "knot", "simple-knot")
BLACK, WHITE = (24,24,27,255), (255,255,255,255)


def instance(name):
    if name == "stick":
        chars = tuple(tuple(row) for row in (ROOT/"examples/context-sensitive/stick.txt").read_text().splitlines())
        source = tuple(tuple(WHITE if cell == "W" else BLACK for cell in row) for row in chars)
        pattern_size, placement_size = 1, 20
    else:
        source = tuple(tuple(row) for row in load_image_grid(ROOT/f"examples/{name}.png"))
        pattern_size = 3
        placement_size = 14 if name == "letter-z" else 8
    patterns, occurrence = extract_pattern_occurrence_grid(source, pattern_size)
    allowed = build_compatibility(patterns)
    cnf = patterns_to_cnf(patterns, allowed, placement_size, placement_size)
    specs = tuple(PatternSpec(p.id,p.frequency,pattern_size,pattern_size,
        bytes(channel for row in p.rows for pixel in row for channel in pixel)) for p in patterns)
    placements = tuple(Placement(var,x,y,pid) for var,(x,y,pid) in sorted(cnf.name_map.items()))
    mapping = MappingSpec(placement_size,placement_size,specs,placements,allowed,occurrence)
    mapping.validate(cnf.num_vars)
    model = WFCModel.from_patterns(patterns,allowed,occurrence)
    return {"source":source,"patterns":patterns,"occurrence":occurrence,"allowed":allowed,
            "cnf":cnf,"mapping":mapping,"model":model,"pattern_size":pattern_size,
            "placement_size":placement_size}


def decode(patterns, grid):
    if not grid: return ()
    table = {p.id:p.rows for p in patterns}
    n = len(next(iter(table.values())))
    height, width = len(grid)+n-1, len(grid[0])+n-1
    pixels = [[None]*width for _ in range(height)]
    for y,row in enumerate(grid):
        for x,pid in enumerate(row):
            for dy,prow in enumerate(table[pid]):
                for dx,pixel in enumerate(prow):
                    old=pixels[y+dy][x+dx]
                    if old is not None and old != pixel: raise RuntimeError("illegal overlap")
                    pixels[y+dy][x+dx]=pixel
    return tuple(tuple(row) for row in pixels)


def save_grid(grid,path,scale=12):
    from PIL import Image
    image=Image.new("RGBA",(len(grid[0]),len(grid)))
    image.putdata([pixel for row in grid for pixel in row])
    image.resize((image.width*scale,image.height*scale),Image.Resampling.NEAREST).save(path)


def save_failure(path,size=192):
    from PIL import Image, ImageDraw
    image=Image.new("RGBA",(size,size),(244,247,249,255)); draw=ImageDraw.Draw(image)
    draw.line((30,30,size-30,size-30),fill=(194,65,73,255),width=10)
    draw.line((size-30,30,30,size-30),fill=(194,65,73,255),width=10)
    draw.text((size//2-28,size//2-7),"FAILED",fill=(92,43,49,255))
    image.save(path)


def run_wfc(data,decision,seed):
    started=time.perf_counter(); engine=OrdinaryWFC(data["model"],data["placement_size"],data["placement_size"],selection="lexical",decision=decision,seed=seed); result=engine.run()
    grid=tuple(tuple(v for v in row) for row in result.output) if result.success else ()
    return {"engine":"ordinary-wfc","decision":decision,"seed":seed,"success":result.success,
      "contradictions":result.contradictions,"conflicts":None,"backtracks":0,"restarts":0,
      "runtime_seconds":time.perf_counter()-started,"context_lookups":result.context_lookups,
      "context_fallbacks":result.context_fallbacks,"grid":grid}


def run_sat(data,decision,seed):
    from pysat.solvers import Cadical195
    started=time.perf_counter(); observer=DomainObserver(data["mapping"],lambda event:None,heuristic=decision,seed=seed,selection="lexical")
    with Cadical195(bootstrap_with=data["cnf"].clauses,use_timer=True) as solver:
        solver.connect_propagator(observer)
        for p in data["mapping"].placements: solver.observe(p.var)
        success=solver.solve(); model=solver.get_model() or []; stats=solver.accum_stats(); solver.disconnect_propagator()
    grid=()
    if success:
        positive={lit for lit in model if lit>0}; lookup={(p.x,p.y):p.pattern_id for p in data["mapping"].placements if p.var in positive}
        grid=tuple(tuple(lookup[(x,y)] for x in range(data["placement_size"])) for y in range(data["placement_size"]))
    return {"engine":"wfc-as-sat","decision":decision,"seed":seed,"success":bool(success),
      "contradictions":stats.get("conflicts",0),"conflicts":stats.get("conflicts",0),
      "backtracks":observer.backtrack_events,"restarts":stats.get("restarts",0),
      "runtime_seconds":time.perf_counter()-started,"context_lookups":observer.context_lookups,
      "context_fallbacks":observer.context_fallbacks,"grid":grid}


def counts(grid,dx=0,dy=0):
    result=Counter(); height,width=len(grid),len(grid[0])
    if (dx,dy)==(0,0): result.update(pixel for row in grid for pixel in row); return result
    for y in range(height):
        for x in range(width):
            nx,ny=x+dx,y+dy
            if 0<=nx<width and 0<=ny<height: result[(grid[y][x],grid[ny][nx])]+=1
    return result


def kl(target,source):
    tn,sn=sum(target.values()),sum(source.values())
    if not tn or not sn:return None
    p={k:v/tn for k,v in target.items()}; q={k:v/sn for k,v in source.items()}
    if any(q.get(k,0)==0 for k in p):return math.inf
    return sum(v*math.log(v/q[k]) for k,v in p.items())


def add_metrics(record,source,decoded):
    record["output_sha256"] = hashlib.sha256(bytes(channel for row in decoded for pixel in row for channel in pixel)).hexdigest()
    record["metrics"]={"tile":kl(counts(decoded),counts(source)),"horizontal":kl(counts(decoded,1,0),counts(source,1,0)),
      "vertical":kl(counts(decoded,0,1),counts(source,0,1)),"diagonal_se":kl(counts(decoded,1,1),counts(source,1,1)),
      "diagonal_sw":kl(counts(decoded,-1,1),counts(source,-1,1))}
    tagged_target=Counter(); tagged_source=Counter()
    for tag,(dx,dy) in {"H":(1,0),"V":(0,1),"SE":(1,1),"SW":(-1,1)}.items():
        tagged_target.update({(tag,*key):value for key,value in counts(decoded,dx,dy).items()})
        tagged_source.update({(tag,*key):value for key,value in counts(source,dx,dy).items()})
    record["metrics"]["local8_tagged"]=kl(tagged_target,tagged_source)
    if record["benchmark"]=="letter-z":
        record["diagonal_lag"]={}
        for lag in (1,2,4,8):
            record["diagonal_lag"][str(lag)]={"se":kl(counts(decoded,lag,lag),counts(source,lag,lag)),"sw":kl(counts(decoded,-lag,lag),counts(source,-lag,lag))}


def finite_mean(values):
    finite=[v for v in values if v is not None and math.isfinite(v)]
    return statistics.mean(finite) if finite else None


def summarize(records):
    result=[]
    for benchmark in BENCHMARKS:
      for engine in ("ordinary-wfc","wfc-as-sat"):
       for decision in DECISIONS:
        group=[r for r in records if r["benchmark"]==benchmark and r["engine"]==engine and r["decision"]==decision]
        success=[r for r in group if r["success"]]
        metrics={key:finite_mean([r["metrics"][key] for r in success]) for key in ("tile","horizontal","vertical","diagonal_se","diagonal_sw","local8_tagged")}
        item={"benchmark":benchmark,"engine":engine,"decision":decision,"runs":len(group),"successes":len(success),
          "contradictions":sum(r["contradictions"] for r in group),"conflicts":sum(r["conflicts"] or 0 for r in group),
          "backtracks":sum(r["backtracks"] for r in group),"runtime_seconds":sum(r["runtime_seconds"] for r in group),
          "context_lookups":sum(r["context_lookups"] for r in group),"context_fallbacks":sum(r["context_fallbacks"] for r in group),
          "fallback_rate":sum(r["context_fallbacks"] for r in group)/sum(r["context_lookups"] for r in group) if sum(r["context_lookups"] for r in group) else 0,
          "metrics":metrics,"infinite_metrics":{key:sum(math.isinf(r["metrics"][key]) for r in success) for key in metrics}}
        if benchmark=="letter-z":
          item["diagonal_lag"]={str(lag):{axis:finite_mean([r["diagonal_lag"][str(lag)][axis] for r in success]) for axis in ("se","sw")} for lag in (1,2,4,8)}
        result.append(item)
    return result


def fmt(value):
    if value is None:return "—"
    if isinstance(value,float) and math.isinf(value):return "∞"
    return f"{value:.4f}"


def report(summary):
    cards=[]
    for name in BENCHMARKS:
      cards.append(f'<section><h2>{name}</h2><div class="gallery"><article><h3>Source</h3><img src="{name}-source.png"></article>')
      for decision in DECISIONS:
       for engine in ("ordinary-wfc","wfc-as-sat"):
        row=next(s for s in summary if s["benchmark"]==name and s["engine"]==engine and s["decision"]==decision)
        cards.append(f'<article><h3>{LABELS[decision]} · {engine}</h3><img src="{name}-{decision}-{engine}-seed-0.png"><p>{row["successes"]}/{row["runs"]} success · fallback {row["fallback_rate"]:.1%}</p></article>')
      cards.append('</div><table><tr><th>Condition</th><th>Engine</th><th>Tile</th><th>Horizontal</th><th>Vertical</th><th>Diagonal SE</th><th>Diagonal SW</th><th>8-neighbor</th><th>Fallback</th></tr>')
      for row in [s for s in summary if s["benchmark"]==name]:
       m=row["metrics"]; cards.append(f'<tr><td>{LABELS[row["decision"]]}</td><td>{row["engine"]}</td>'+''.join(f'<td>{fmt(m[k])}</td>' for k in ("tile","horizontal","vertical","diagonal_se","diagonal_sw","local8_tagged"))+f'<td>{row["fallback_rate"]:.1%}</td></tr>')
      cards.append('</table></section>')
    zrows=[s for s in summary if s["benchmark"]=="letter-z"]
    lagrows=''.join(f'<tr><td>{LABELS[r["decision"]]}</td><td>{r["engine"]}</td>'+''.join(f'<td>{fmt(r["diagonal_lag"][str(lag)][axis])}</td>' for lag in (1,2,4,8) for axis in ("se","sw"))+'</tr>' for r in zrows)
    html='''<!doctype html><html><head><meta charset="utf-8"><title>Moore context experiment</title><style>body{font:14px/1.4 system-ui;margin:2rem;background:#eef3f6;color:#142b3b}main{max-width:1450px}h1{font-size:32px}.control{padding:1rem;background:#dff5ef;border-left:6px solid #168b75;font-weight:700}.diagrams{display:flex;gap:4rem;background:white;padding:1rem 2rem;white-space:pre;font:16px/1.35 monospace}.gallery{display:flex;flex-wrap:wrap;gap:.7rem}article{width:180px;background:white;border:1px solid #ccd9e0;padding:.65rem}img{width:160px;height:160px;object-fit:contain;image-rendering:pixelated}table{width:100%;border-collapse:collapse;background:white;font-size:12px}th,td{border:1px solid #ccd9e0;padding:.35rem;text-align:right}th:first-child,td:first-child{text-align:left}section{margin:2.2rem 0}.finding{background:#fff;padding:1rem;border-left:6px solid #168b75}</style></head><body><main><h1>4-neighbor vs 8-neighbor context</h1><div class="diagrams"><div><b>von Neumann / rook</b>\n\n    N\nW   x   E\n    S</div><div><b>Moore / king</b>\n\nNW  N  NE\n W  x   E\nSW  S  SE</div></div><p class="control">The experiment changes only which neighboring tiles influence the choice; the hard legal adjacency rules remain unchanged.</p><p>Matched seeds; Context-4 order N,E,S,W; Context-8 order N,NE,E,SE,S,SW,W,NW. Smaller fidelity differences are better. Infinite means output mass outside source support.</p><div class="finding"><b>Result:</b> Moore is not uniformly superior. It provides a small average letter-Z diagonal improvement, is strongest on Knot, is mixed on Cat, and is worse on Simple Knot. The seed-0 letter-Z output does not visibly preserve a complete Z under any condition.</div>'''+''.join(cards)+'''<section><h2>Letter-Z diagonal lag detail</h2><table><tr><th>Condition</th><th>Engine</th><th>r1 SE</th><th>r1 SW</th><th>r2 SE</th><th>r2 SW</th><th>r4 SE</th><th>r4 SW</th><th>r8 SE</th><th>r8 SW</th></tr>'''+lagrows+'''</table></section><section><h2>Interpretation</h2><ol><li>Moore does not clearly improve the visible seed-0 Z; all displayed methods produce fragments rather than a complete letter.</li><li>Across matched runs, Moore slightly improves letter-Z diagonal-pair and tagged local-8 scores versus Context-4.</li><li>Letter-Z horizontal resemblance improves slightly; vertical is essentially tied for ordinary WFC and improves for SAT.</li><li>Moore fallback is zero for letter-Z, but rises versus Context-4 on Stick, Cat, Knot, and especially Simple Knot.</li><li>The effect is image-dependent: positive on Knot, mixed on Cat, negative on Simple Knot.</li><li>Stick is conflict-free and ordinary WFC/SAT output hashes agree per matched condition and seed.</li><li>In conflict cases, Moore sharply reduces letter-Z SAT conflicts but increases Simple Knot conflicts; CDCL interaction is also image-dependent.</li></ol></section><section><h2>Scope and limitations</h2><p>Stick and letter-z use 20 matched seeds. Cat, knot, and simple-knot use five matched seeds. Failed runs remain in success and search statistics. Fidelity means are over successful finite measurements only; the table and raw JSON record infinity counts and per-seed values. These are modest samples, visible structure is not fully captured by pair statistics, output and source sizes can differ, and no significance tests were performed. Repository: <a href="https://github.com/stevex24/wfc-to-sat/tree/moore-context-experiment">moore-context-experiment</a>.</p></section></main></body></html>'''
    (OUT/"index.html").write_text(html,encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--quick",action="store_true"); args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True); records=[]
    for name in BENCHMARKS:
        data=instance(name); save_grid(data["source"],OUT/f"{name}-source.png")
        seeds=range(1 if args.quick else (20 if name in {"stick","letter-z"} else 5))
        for seed in seeds:
          for decision in DECISIONS:
            for runner in (run_wfc,run_sat):
              record=runner(data,decision,seed); record["benchmark"]=name; record["pattern_size"]=data["pattern_size"]
              if record["success"]:
                decoded=decode(data["patterns"],record.pop("grid")); add_metrics(record,data["source"],decoded)
                if seed==0: save_grid(decoded,OUT/f'{name}-{decision}-{record["engine"]}-seed-0.png')
              else:
                record.pop("grid"); record["metrics"]={}
                if seed==0: save_failure(OUT/f'{name}-{decision}-{record["engine"]}-seed-0.png')
              records.append(record)
              print(name,seed,decision,record["engine"],record["success"],f'{record["runtime_seconds"]:.3f}s')
    summary=summarize(records)
    payload={"metadata":{"generated_utc":datetime.now(timezone.utc).isoformat(),"branch":"moore-context-experiment","starting_commit":"e4db3198c755e4f0539878716acec03d1ce6db2f","neighborhoods":{"von_neumann":[[0,-1],[1,0],[0,1],[-1,0]],"moore":[[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1]]},"hard_constraints":"unchanged orthogonal overlap compatibility"},"summary":summary,"runs":records}
    (OUT/"results.json").write_text(json.dumps(payload,indent=2,allow_nan=True)+"\n")
    report(summary)


if __name__=="__main__": main()
