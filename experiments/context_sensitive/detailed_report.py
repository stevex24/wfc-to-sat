#!/usr/bin/env python3
"""Recover saved measurements and render the original-spec compliance report."""

from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
import statistics
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.lag_r_metrics import lag_kl, lag_pair_counts, normalized, kl_target_source
from experiments.context_sensitive.zelda_experiment import tile_source

OUT = ROOT / "context-sensitive-results/detailed-comparison"
MISSING_SAT = "MISSING — one-seed pilot exceeded 90 seconds and was stopped; 100-run rerun not launched"
MISSING_3 = "MISSING — no saved Zelda N=3 outputs; current 2,958-pattern SAT compiler scale is impractical"
FIELDS = ["example","N","heuristic","runs","wfc_pattern_frequency_kl","sat_pattern_frequency_kl",
          "wfc_pattern_edge_frequency_kl","sat_pattern_edge_frequency_kl","wfc_decoded_tile_frequency_kl",
          "sat_decoded_tile_frequency_kl","wfc_decoded_tile_edge_frequency_kl","sat_decoded_tile_edge_frequency_kl",
          "wfc_successes","sat_successes"]


def load(path):
    return json.loads((ROOT / path).read_text())


def summary_map(items):
    return {(item["engine"], item["decision"]): item for item in items}


def value(item, key):
    return item.get(key, "MISSING") if item else "MISSING"


def main_rows():
    stick = summary_map(load("context-sensitive-results/core-comparison/summary.json"))
    zelda_data = load("context-sensitive-results/detailed-comparison/raw/zelda-1x1.json")
    zelda = summary_map(zelda_data["summary"])
    rows = []
    for example, summaries, decisions in (("Stick", stick, ("uniform","frequency","context")),
                                            ("Zelda", zelda, ("uniform","frequency","context"))):
        for decision in decisions:
            w = summaries.get(("ordinary WFC", decision)); s = summaries.get(("WFC-as-SAT", decision))
            sat_missing = MISSING_SAT if example == "Zelda" else "MISSING"
            wp, we = value(w,"pooled_tile_kl"), value(w,"pooled_edge_kl")
            sp = value(s,"pooled_tile_kl") if s else sat_missing
            se = value(s,"pooled_edge_kl") if s else sat_missing
            rows.append(dict(zip(FIELDS,[example,1,decision,w["runs"] if w else (s["runs"] if s else 0),
                wp,sp,we,se,wp,sp,we,se,w["successes"] if w else 0,s["successes"] if s else sat_missing])))
    plain = stick[("Plain SAT/CDCL","solver")]
    rows.append(dict(zip(FIELDS,["Stick",1,"Plain SAT",plain["runs"],"N/A",plain["pooled_tile_kl"],
        "N/A",plain["pooled_edge_kl"],"N/A",plain["pooled_tile_kl"],"N/A",plain["pooled_edge_kl"],"N/A",plain["successes"]])))
    for decision in ("uniform","frequency","context","Plain SAT"):
        rows.append(dict(zip(FIELDS,["Zelda",3,decision,0,MISSING_3,MISSING_3,MISSING_3,MISSING_3,
                                     MISSING_3,MISSING_3,MISSING_3,MISSING_3,0,0])))
    return rows


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)


def per_run_rows():
    rows=[]
    for example,path in (("Stick","context-sensitive-results/core-comparison/raw-runs.json"),
                         ("Zelda","context-sensitive-results/detailed-comparison/raw/zelda-1x1.json")):
        data=load(path); records=data["runs"]
        for r in records:
            tile=r.get("tile_kl",""); edge=r.get("edge_kl","")
            rows.append({"example":example,"N":1,"engine":r["engine"],"heuristic":r["decision"],"seed":r["seed"],
                "success":r["success"],"pattern_frequency_kl":tile,"pattern_edge_frequency_kl":edge,
                "decoded_tile_frequency_kl":tile,"decoded_tile_edge_frequency_kl":edge,
                "runtime_seconds":r["runtime_seconds"],"conflicts":r.get("conflicts","N/A"),"backtracks":r.get("backtracks","N/A")})
    return rows


def performance_rows():
    rows=[]
    for example,path,key in (("Stick","context-sensitive-results/core-comparison/summary.json",None),
                             ("Zelda","context-sensitive-results/detailed-comparison/raw/zelda-1x1.json","summary")):
        data=load(path); items=data if key is None else data[key]
        for s in items:
            rt=s.get("runtime_seconds",{})
            rows.append({"example":example,"N":1,"engine":s["engine"],"heuristic":s["decision"],"runs":s["runs"],
                "average_runtime_seconds":rt.get("mean",""),"median_runtime_seconds":rt.get("median",""),
                "runtime_stdev_seconds":rt.get("stdev",""),"peak_memory":"NOT MEASURED",
                "average_conflicts":s.get("conflicts",{}).get("mean","N/A"),
                "average_backtracks":s.get("backtracks",{}).get("mean","N/A"),"successes":s["successes"],"failures":s["runs"]-s["successes"]})
    return rows


def lag_analysis(zelda_runs):
    source,_=tile_source(); lags=(1,2,4,8,16); axes=("horizontal","vertical"); result=[]
    for decision in ("uniform","frequency","context"):
        grids=[tuple(tuple(row) for row in r["output"]) for r in zelda_runs if r["decision"]==decision and r["success"]]
        for axis in axes:
            for lag in lags:
                pooled=lag_kl(grids,source,lag,axis)
                source_dist=normalized(lag_pair_counts(source,lag,axis)); per=[]
                for grid in grids:
                    per.append(kl_target_source(normalized(lag_pair_counts(grid,lag,axis)),source_dist))
                finite=[x for x in per if math.isfinite(x)]
                result.append({"example":"Zelda","N":1,"engine":"ordinary WFC","heuristic":decision,"axis":axis,"lag":lag,
                    "pooled_kl":pooled,"per_run_mean":statistics.mean(finite) if finite else math.inf,
                    "per_run_median":statistics.median(finite) if finite else math.inf,
                    "per_run_stdev":statistics.stdev(finite) if len(finite)>1 else 0,"sample_count":len(per),
                    "finite_count":len(finite),"infinite_count":len(per)-len(finite)})
    payload={"metadata":{"source":"authors' Zelda map; 16x16 tiles","direction":"generated P || source Q",
              "pairs":"ordered, axis-specific, finite/nonperiodic boundaries","note":"r=32 unavailable for 20x20 outputs"},"rows":result}
    (OUT/"raw/zelda-1x1-lag-r.json").write_text(json.dumps(payload,indent=2,allow_nan=True)+"\n")
    return result


def render_zelda_seed(records):
    _,rgba=tile_source(); dest=OUT/"images"; dest.mkdir(parents=True,exist_ok=True)
    Image.open(ROOT/"examples/context-sensitive/zelda-map-authors.png").save(dest/"zelda-source.png")
    for decision in ("uniform","frequency","context"):
        record=next(r for r in records if r["seed"]==0 and r["decision"]==decision)
        image=Image.new("RGBA",(320,320))
        for y,row in enumerate(record["output"]):
            for x,tile in enumerate(row):
                tile_image=Image.frombytes("RGBA",(16,16),rgba[ord(tile)-0x1000])
                image.paste(tile_image,(x*16,y*16))
        image.save(dest/f"zelda-1x1-{decision}-ordinary-wfc-seed-0.png")


def table(fields,rows):
    return "<table><thead><tr>"+"".join(f"<th>{html.escape(f.replace('_',' '))}</th>" for f in fields)+"</tr></thead><tbody>"+"".join(
        "<tr>"+"".join(f"<td>{html.escape(str(r.get(f,'')))}</td>" for f in fields)+"</tr>" for r in rows)+"</tbody></table>"


def build_html(rows, stats, performance, lag):
    primary_stats=[]
    for example in ("Stick","Zelda"):
        for engine in ("ordinary WFC","WFC-as-SAT","Plain SAT/CDCL"):
            for decision in ("uniform","frequency","context","solver"):
                group=[r for r in stats if r["example"]==example and r["engine"]==engine and r["heuristic"]==decision and r["success"]]
                if not group: continue
                for metric in ("decoded_tile_frequency_kl","decoded_tile_edge_frequency_kl"):
                    vals=[float(r[metric]) for r in group]
                    primary_stats.append({"example":example,"engine":engine,"heuristic":decision,"metric":metric,
                        "mean":statistics.mean(vals),"median":statistics.median(vals),"stdev":statistics.stdev(vals) if len(vals)>1 else 0,
                        "sample_count":len(vals),"success_count":len(group)})
    benchmark=load("context-sensitive-results/meeting-report/benchmarks/raw-runs.json")
    compliance=[
      ("5-7","WFC/SAT heuristic conditions, freq(x,c), SAT restoration","COMPLETE","implementation and automated tests","Zelda pilot exposed and fixed skipped-level synchronization"),
      ("8,11","Overlapping 3x3 and four distinct KL measures","PARTIAL","results.csv retains all four columns","periodic extraction implemented/tested; no N=3 generations"),
      ("9","Matched WFC vs WFC-as-SAT validation","PARTIAL","Stick rows and raw-runs.json","Stick complete; Zelda SAT missing"),
      ("10","Stick 100x20x20","COMPLETE","main table / core-comparison/raw-runs.json","all conditions; Plain SAT deterministic once"),
      ("10","Zelda 1x1 100x20x20","PARTIAL","main table / raw/zelda-1x1.json","ordinary WFC complete; SAT pilot too costly"),
      ("10","Zelda overlapping 3x3 100x20x20","NOT DONE","main table","no saved outputs; compiler scale blocker"),
      ("12","Pooled and per-run statistics","PARTIAL","statistical table / per-run.csv","complete for generated primary arms"),
      ("13","Zelda 1x1 and 3x3 lag-r","PARTIAL","lag-r table / raw/zelda-1x1-lag-r.json","Zelda 1x1 WFC r1-16; r32 impossible on 20x20; N3 missing"),
      ("14","Contradictions and failures","COMPLETE","performance.csv and benchmark table","failures retained; Simple Maze SAT UNSAT distinguished"),
      ("15","Lexical selection and anisotropy","COMPLETE","scope and lag-r axes","horizontal/vertical separate"),
      ("17","Plain SAT baseline","PARTIAL","Stick main table","deterministic Stick characterized; Zelda missing"),
      ("18","Runtime and peak memory","PARTIAL","performance table","runtime complete where run; peak RSS NOT MEASURED"),
      ("19","Repository benchmark suite","PARTIAL","benchmark table / meeting-report raw data","six inputs, seed 0 only; diagnostic rather than distribution"),
      ("20","One-command script","PARTIAL","run_context_sensitive_experiments.sh","existing Stick/benchmark driver; does not complete Zelda"),
      ("21","Reproducibility metadata","PARTIAL","raw JSON metadata","strong for Stick/Zelda; benchmark metadata incomplete"),
      ("22","Resemblance and performance tables","COMPLETE","results.csv / performance.csv","missing values retained explicitly"),
      ("23","Automated correctness tests","COMPLETE","tests","context, fallback, undo/backtrack, extraction, CNF equivalence"),
      ("25","Required work sequence/documentation","PARTIAL","this compliance table","phases with missing Zelda remain incomplete"),
    ]
    main_fields=FIELDS
    stat_fields=["example","engine","heuristic","metric","mean","median","stdev","sample_count","success_count"]
    perf_fields=list(performance[0])
    lag_fields=["example","N","engine","heuristic","axis","lag","pooled_kl","per_run_mean","per_run_median","per_run_stdev","sample_count","finite_count","infinite_count"]
    bench_fields=["benchmark","engine","decision","seed","pattern_size","placement_grid","success","runtime_seconds","contradictions"]
    comp_rows=[dict(zip(("section","requirement","status","evidence","notes"),r)) for r in compliance]
    gallery=''.join(f'<article><h3>{d} · ordinary WFC</h3><img src="images/zelda-1x1-{d}-ordinary-wfc-seed-0.png"><p>Uncurated seed 0.</p></article>' for d in ("uniform","frequency","context"))
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Context-sensitive WFC/SAT specification audit</title><style>body{{font:14px/1.45 system-ui;margin:2rem;color:#172033;background:#f3f5f9}}main{{max-width:1800px}}table{{border-collapse:collapse;background:white;font-size:11px;display:block;overflow:auto}}th,td{{border:1px solid #cbd5e1;padding:.35rem;vertical-align:top}}th{{position:sticky;top:0;background:#e2e8f0}}.warn{{border-left:6px solid #be123c;background:#fff;padding:1rem}}.gallery{{display:flex;gap:1rem;flex-wrap:wrap}}article{{background:white;padding:.7rem}}img{{max-width:320px;image-rendering:pixelated}}</style></head><body><main>
<h1>Original context-sensitive WFC/SAT specification: detailed comparison and compliance audit</h1>
<h2>1. Scope and exact configurations</h2><p>Corrective branch <code>spec-completion-report</code> from <code>e4db319</code>. KL direction is generated target P || source Q, natural logarithm, no smoothing; smaller is closer. N=1 pattern and decoded-tile metrics are mathematically identical and are deliberately repeated under explicit labels. Ordinary WFC is this repository's independent standard overlapping-WFC implementation, not Gumin's code. Generated outputs are finite/nonperiodic.</p><p>Verified Zelda N=3 policy: source pattern extraction wraps both axes; output constraints and output-edge metrics do not wrap. Existing nonwrapped extraction remains the default.</p><div class="warn"><b>Acceptance status: PARTIAL.</b> Zelda SAT and Zelda N=3 primary studies are not complete; peak memory is not measured. Missing cells remain visible below.</div>
<h2>2. Main resemblance table</h2>{table(main_fields,rows)}
<h2>3. Per-run and pooled statistical table</h2>{table(stat_fields,primary_stats)}<p>Raw values: <a href="per-run.csv">per-run.csv</a>. Pooled values are in the main table and are not means of per-run KL.</p>
<h2>4. Performance table</h2>{table(perf_fields,performance)}
<h2>5. Primary Stick/Zelda results</h2><p>Stick is complete and reproduces the paper approximately. Zelda 1x1 ordinary WFC is complete for 100 seeds; matched SAT is missing after the measured pilot. Zelda 3x3 is not generated.</p>
<h2>6. WFC-vs-SAT equivalence/control results</h2><p>For Stick, all 100 matched output grids are exactly identical for uniform, frequency, and context because no conflicts/backtracks occurred. This is stronger than aggregate similarity but applies only to the conflict-free case. Benchmark conflict cases differ; SAT CDCL can recover where stop-on-contradiction WFC fails.</p>
<h2>7. Required lag-r results</h2>{table(lag_fields,lag)}<p>r=32 is unavailable by definition on a 20x20 output. Zelda N=3 lag-r remains missing.</p>
<h2>8. Existing benchmark results</h2>{table(bench_fields,benchmark)}<p>These are repository-configured N=3, 8x8-placement seed-0 diagnostics, not primary distribution estimates. Simple Maze is a genuinely UNSAT SAT encoding in this configuration; ordinary-WFC contradiction is separately a search failure.</p>
<h2>9. Representative images</h2><div class="gallery"><article><h3>Zelda source</h3><img src="images/zelda-source.png"></article>{gallery}</div>
<h2>10. Limitations / unavailable values</h2><ul><li>Zelda SAT pilot exceeded 90 seconds before completing one seed; 100 runs were not launched.</li><li>Zelda N=3 has 2,958 patterns; the existing exact-one encoding alone is over 1.7 billion pair clauses at 20x20, so no faithful SAT run was launched.</li><li>Peak RSS was never captured by saved runs and was not fabricated.</li><li>The paper permits blank contradictions or backtracking, whereas this ordinary WFC stops at contradiction and SAT uses CDCL; these policies are reported, not equated.</li></ul>
<h2>11. Requirement-compliance table</h2>{table(["section","requirement","status","evidence","notes"],comp_rows)}
<h2>12. Exact reproduction commands</h2><pre>python -m unittest tests.test_pattern_semantics tests.test_cnf_semantics tests.test_sat_context_heuristics
python experiments/context_sensitive/zelda_experiment.py --runs 100 --engine ordinary
python experiments/context_sensitive/detailed_report.py
open context-sensitive-results/detailed-comparison/index.html</pre>
</main></body></html>'''


def main():
    OUT.mkdir(parents=True,exist_ok=True); (OUT/"raw").mkdir(exist_ok=True)
    rows=main_rows(); stats=per_run_rows(); performance=performance_rows()
    zelda=load("context-sensitive-results/detailed-comparison/raw/zelda-1x1.json")
    zelda["metadata"].update({
        "execution_base_commit": "e4db319f22181599127127b172a06c30ddf11b9d",
        "analysis_code_commit": "5c4069d",
        "pilot": "matched SAT pilot stopped after >90 seconds before one seed completed",
    })
    (OUT/"raw/zelda-1x1.json").write_text(json.dumps(zelda,indent=2)+"\n",encoding="utf-8")
    lag=lag_analysis(zelda["runs"]); render_zelda_seed(zelda["runs"])
    write_csv(OUT/"results.csv",FIELDS,rows)
    write_csv(OUT/"per-run.csv",list(stats[0]),stats)
    write_csv(OUT/"performance.csv",list(performance[0]),performance)
    (OUT/"index.html").write_text(build_html(rows,stats,performance,lag),encoding="utf-8")
    print(OUT/"index.html")


if __name__ == "__main__": main()
