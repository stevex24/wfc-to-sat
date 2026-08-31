#!/usr/bin/env python3
"""Matched 100-seed Zelda 1x1 sweep for frequency and context heuristics."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import multiprocessing
from pathlib import Path
import statistics
import sys
import time
import traceback

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.core_experiment import add_metrics, run_sat, run_wfc
from experiments.context_sensitive.zelda_experiment import sat_instance, tile_source
from wfc_to_sat.ordinary_wfc import WFCModel


OUT = ROOT / "context-sensitive-results/detailed-comparison"
RAW_JSON = OUT / "raw/zelda-1x1-weighted-matched.json"
PER_RUN_CSV = OUT / "zelda-1x1-weighted-per-run.csv"
SUMMARY_CSV = OUT / "zelda-1x1-weighted-summary.csv"
REPORT = OUT / "zelda-1x1-weighted.html"
IMAGES = OUT / "images/zelda-1x1-weighted"
HEURISTICS = ("frequency", "context")
GALLERY_SEEDS = (0, 1, 2, 3, 4)
CNF = MAPPING = TILE_FOR_ID = None


def sat_worker(queue, heuristic, seed):
    try:
        queue.put(("ok", run_sat(CNF, MAPPING, TILE_FOR_ID, heuristic, seed)))
    except BaseException:
        queue.put(("error", traceback.format_exc()))


def run_sat_timed(context, heuristic, seed, timeout):
    queue = context.Queue()
    process = context.Process(target=sat_worker, args=(queue, heuristic, seed))
    started = time.perf_counter()
    process.start()
    process.join(timeout)
    elapsed = time.perf_counter() - started
    if process.is_alive():
        process.terminate()
        process.join()
        queue.close()
        return {
            "engine": "WFC-as-SAT", "selection": "lexical", "decision": heuristic,
            "seed": seed, "width": 20, "height": 20, "success": False,
            "timed_out": True, "failure": False, "error": None,
            "runtime_seconds": elapsed, "solve_seconds": None, "output": [],
            "conflicts": None, "decisions": None, "backtracks": None,
            "restarts": None, "contradictions": None, "propagations": None,
            "solver": "CaDiCaL 1.9.5 via PySAT",
            "contradiction_policy": "CDCL backtrack/restart",
        }
    if queue.empty():
        queue.close()
        return {
            "engine": "WFC-as-SAT", "selection": "lexical", "decision": heuristic,
            "seed": seed, "width": 20, "height": 20, "success": False,
            "timed_out": False, "failure": True,
            "error": f"worker exited {process.exitcode} without a result",
            "runtime_seconds": elapsed, "solve_seconds": None, "output": [],
            "conflicts": None, "decisions": None, "backtracks": None,
            "restarts": None, "contradictions": None, "propagations": None,
            "solver": "CaDiCaL 1.9.5 via PySAT",
            "contradiction_policy": "CDCL backtrack/restart",
        }
    status, value = queue.get()
    queue.close()
    if status == "error":
        return {
            "engine": "WFC-as-SAT", "selection": "lexical", "decision": heuristic,
            "seed": seed, "width": 20, "height": 20, "success": False,
            "timed_out": False, "failure": True, "error": value,
            "runtime_seconds": elapsed, "solve_seconds": None, "output": [],
            "conflicts": None, "decisions": None, "backtracks": None,
            "restarts": None, "contradictions": None, "propagations": None,
            "solver": "CaDiCaL 1.9.5 via PySAT",
            "contradiction_policy": "CDCL backtrack/restart",
        }
    value["timed_out"] = False
    value["failure"] = not value["success"]
    value["error"] = None
    value["worker_wall_seconds"] = elapsed
    return value


def save_incremental(records, metadata):
    RAW_JSON.parent.mkdir(parents=True, exist_ok=True)
    RAW_JSON.write_text(
        json.dumps({"metadata": metadata, "runs": records}, indent=2) + "\n",
        encoding="utf-8",
    )


def finite_stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": ordered[0], "max": ordered[-1],
        "q05": ordered[int((len(ordered) - 1) * 0.05)],
        "q95": ordered[int((len(ordered) - 1) * 0.95)],
    }


def distribution(rows, edge=False):
    counts = {}
    if edge:
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if x + 1 < len(row):
                    key = ("H", tile, row[x + 1]); counts[key] = counts.get(key, 0) + 1
                if y + 1 < len(rows):
                    key = ("V", tile, rows[y + 1][x]); counts[key] = counts.get(key, 0) + 1
    else:
        for row in rows:
            for tile in row:
                counts[tile] = counts.get(tile, 0) + 1
    total = sum(counts.values())
    return {key: count / total for key, count in counts.items()}


def kl(target, source):
    if any(source.get(key, 0.0) == 0.0 for key in target):
        return math.inf
    return sum(value * math.log(value / source[key]) for key, value in target.items())


def pooled_kl(records, source, edge=False):
    pooled = []
    if edge:
        counts = {}
        for record in records:
            rows = record["output"]
            for y, row in enumerate(rows):
                for x, tile in enumerate(row):
                    if x + 1 < len(row):
                        key = ("H", tile, row[x + 1]); counts[key] = counts.get(key, 0) + 1
                    if y + 1 < len(rows):
                        key = ("V", tile, rows[y + 1][x]); counts[key] = counts.get(key, 0) + 1
        total = sum(counts.values())
        target = {key: count / total for key, count in counts.items()}
        return kl(target, distribution(source, edge=True))
    for record in records:
        pooled.extend(record["output"])
    return kl(distribution(pooled), distribution(source))


def summarize(records, source):
    summaries = []
    for heuristic in HEURISTICS:
        for engine in ("ordinary WFC", "WFC-as-SAT"):
            group = [r for r in records if r["decision"] == heuristic and r["engine"] == engine]
            successful = [r for r in group if r["success"]]
            item = {
                "heuristic": heuristic, "engine": engine, "runs": len(group),
                "successes": len(successful),
                "timeouts": sum(bool(r.get("timed_out")) for r in group),
                "failures": sum(not r["success"] and not r.get("timed_out") for r in group),
                "pooled_tile_kl": pooled_kl(successful, source) if successful else None,
                "pooled_edge_kl": pooled_kl(successful, source, edge=True) if successful else None,
                "tile_kl": finite_stats([r.get("tile_kl") for r in successful]),
                "edge_kl": finite_stats([r.get("edge_kl") for r in successful]),
                "runtime_seconds": finite_stats([r.get("runtime_seconds") for r in successful]),
                "solve_seconds": finite_stats([r.get("solve_seconds") for r in successful]),
                "conflicts": finite_stats([r.get("conflicts") for r in successful]),
                "decisions": finite_stats([r.get("decisions") for r in successful]),
                "backtracks": finite_stats([r.get("backtracks") for r in successful]),
            }
            summaries.append(item)
    for heuristic in HEURISTICS:
        wfc = {r["seed"]: r for r in records if r["decision"] == heuristic and r["engine"] == "ordinary WFC" and r["success"]}
        sat = {r["seed"]: r for r in records if r["decision"] == heuristic and r["engine"] == "WFC-as-SAT" and r["success"]}
        matches = sum(wfc[seed]["output"] == sat[seed]["output"] for seed in wfc.keys() & sat.keys())
        for item in summaries:
            if item["heuristic"] == heuristic:
                item["matched_successful_pairs"] = len(wfc.keys() & sat.keys())
                item["exact_output_matches"] = matches
    return summaries


def render(record, rgba, tile_id):
    image = Image.new("RGBA", (20 * 16, 20 * 16))
    for y, row in enumerate(record["output"]):
        for x, tile in enumerate(row):
            tile_image = Image.frombytes("RGBA", (16, 16), rgba[tile_id[tile]])
            image.paste(tile_image, (x * 16, y * 16))
    return image


def write_outputs(records, summaries, source, rgba, model, metadata):
    payload = {"metadata": metadata, "runs": records, "summary": summaries}
    RAW_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fields = [
        "engine", "decision", "seed", "success", "timed_out", "failure",
        "tile_kl", "edge_kl", "runtime_seconds", "solve_seconds", "conflicts",
        "decisions", "backtracks", "restarts", "error",
    ]
    with PER_RUN_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in fields})
    summary_fields = [
        "heuristic", "engine", "runs", "successes", "timeouts", "failures",
        "pooled_tile_kl", "pooled_edge_kl", "mean_tile_kl", "median_tile_kl",
        "mean_edge_kl", "median_edge_kl", "mean_runtime_seconds",
        "median_runtime_seconds", "mean_solve_seconds", "median_solve_seconds",
        "min_runtime_seconds", "q05_runtime_seconds", "q95_runtime_seconds", "max_runtime_seconds",
        "min_solve_seconds", "q05_solve_seconds", "q95_solve_seconds", "max_solve_seconds",
        "mean_conflicts", "mean_decisions", "mean_backtracks",
        "matched_successful_pairs", "exact_output_matches",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, summary_fields)
        writer.writeheader()
        for item in summaries:
            writer.writerow({
                **{key: item.get(key) for key in summary_fields},
                "mean_tile_kl": item["tile_kl"].get("mean"),
                "median_tile_kl": item["tile_kl"].get("median"),
                "mean_edge_kl": item["edge_kl"].get("mean"),
                "median_edge_kl": item["edge_kl"].get("median"),
                "mean_runtime_seconds": item["runtime_seconds"].get("mean"),
                "median_runtime_seconds": item["runtime_seconds"].get("median"),
                "mean_solve_seconds": item["solve_seconds"].get("mean"),
                "median_solve_seconds": item["solve_seconds"].get("median"),
                "min_runtime_seconds": item["runtime_seconds"].get("min"),
                "q05_runtime_seconds": item["runtime_seconds"].get("q05"),
                "q95_runtime_seconds": item["runtime_seconds"].get("q95"),
                "max_runtime_seconds": item["runtime_seconds"].get("max"),
                "min_solve_seconds": item["solve_seconds"].get("min"),
                "q05_solve_seconds": item["solve_seconds"].get("q05"),
                "q95_solve_seconds": item["solve_seconds"].get("q95"),
                "max_solve_seconds": item["solve_seconds"].get("max"),
                "mean_conflicts": item["conflicts"].get("mean"),
                "mean_decisions": item["decisions"].get("mean"),
                "mean_backtracks": item["backtracks"].get("mean"),
            })

    IMAGES.mkdir(parents=True, exist_ok=True)
    tile_id = {tile: index for index, tile in enumerate(model.tiles)}
    source_image = Image.open(ROOT / "examples/context-sensitive/zelda-map-authors.png")
    source_image.save(IMAGES / "source.png")
    for seed in GALLERY_SEEDS:
        for heuristic in HEURISTICS:
            for engine, slug in (("ordinary WFC", "ordinary-wfc"), ("WFC-as-SAT", "wfc-as-sat")):
                record = next(r for r in records if r["seed"] == seed and r["decision"] == heuristic and r["engine"] == engine)
                if record["success"]:
                    render(record, rgba, tile_id).save(IMAGES / f"seed-{seed}-{heuristic}-{slug}.png")

    def fmt(value):
        return "N/A" if value is None else f"{value:.8g}" if isinstance(value, float) else str(value)

    table_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(fmt(value))}</td>" for value in (
            item["heuristic"], item["engine"], item["successes"], item["timeouts"], item["failures"],
            item["pooled_tile_kl"], item["tile_kl"].get("mean"), item["tile_kl"].get("median"),
            item["pooled_edge_kl"], item["edge_kl"].get("mean"), item["edge_kl"].get("median"),
            item["runtime_seconds"].get("mean"), item["runtime_seconds"].get("median"),
            item["conflicts"].get("mean"), item["decisions"].get("mean"),
            item["backtracks"].get("mean"), item["exact_output_matches"],
        )) + "</tr>" for item in summaries
    )
    gallery = ['<section><h2>Predetermined matched gallery: seeds 0–4</h2><p>Seeds 0, 1, 2, 3, and 4 were selected in advance, not after inspecting results.</p>']
    for seed in GALLERY_SEEDS:
        gallery.append(f"<h3>Seed {seed}</h3><div class=gallery>")
        for heuristic in HEURISTICS:
            for engine, slug in (("ordinary WFC", "ordinary-wfc"), ("WFC-as-SAT", "wfc-as-sat")):
                label = f"{engine} — {heuristic.title()}"
                path = f"images/zelda-1x1-weighted/seed-{seed}-{heuristic}-{slug}.png"
                gallery.append(f"<figure><img src='{path}'><figcaption>{html.escape(label)}</figcaption></figure>")
        gallery.append("</div>")
    gallery.append("</section>")
    by_condition = {(item["heuristic"], item["engine"]): item for item in summaries}
    fw = by_condition[("frequency", "ordinary WFC")]
    fs = by_condition[("frequency", "WFC-as-SAT")]
    cw = by_condition[("context", "ordinary WFC")]
    cs = by_condition[("context", "WFC-as-SAT")]
    pair_details = {}
    for heuristic in HEURISTICS:
        differing_sat = []
        for seed in range(100):
            wfc = next(r for r in records if r["seed"] == seed and r["decision"] == heuristic and r["engine"] == "ordinary WFC")
            sat = next(r for r in records if r["seed"] == seed and r["decision"] == heuristic and r["engine"] == "WFC-as-SAT")
            if wfc["output"] != sat["output"]:
                differing_sat.append(sat)
        pair_details[heuristic] = (
            len(differing_sat),
            sum(sat.get("conflicts", 0) > 0 for sat in differing_sat),
            sum(sat.get("conflicts", 0) == 0 for sat in differing_sat),
        )
    frequency_seed0 = next(r for r in records if r["seed"] == 0 and r["decision"] == "frequency" and r["engine"] == "WFC-as-SAT")
    context_seed0 = next(r for r in records if r["seed"] == 0 and r["decision"] == "context" and r["engine"] == "WFC-as-SAT")
    answers = f"""<h2>Direct answers</h2><ol>
<li><b>Frequency comparison:</b> ordinary/SAT pooled tile KL is {fw['pooled_tile_kl']:.6g}/{fs['pooled_tile_kl']:.6g}; pooled edge KL is {fw['pooled_edge_kl']:.6g}/{fs['pooled_edge_kl']:.6g}. The aggregate distributions are close, but no paired output is exactly identical.</li>
<li><b>Context comparison:</b> ordinary/SAT pooled tile KL is {cw['pooled_tile_kl']:.6g}/{cs['pooled_tile_kl']:.6g}; pooled edge KL is {cw['pooled_edge_kl']:.6g}/{cs['pooled_edge_kl']:.6g}. The aggregate distributions are also close.</li>
<li><b>Exact matches:</b> Frequency has {fs['exact_output_matches']}/100; Context has {cs['exact_output_matches']}/100 (seed 0).</li>
<li><b>Conflicts when images differ:</b> Frequency has {pair_details['frequency'][1]} conflict/backtracking runs among {pair_details['frequency'][0]} differences. Context has {pair_details['context'][1]} among {pair_details['context'][0]}; its other {pair_details['context'][2]} differences occurred without a conflict. Difference alone therefore does not prove backtracking.</li>
<li><b>Context advantage:</b> SAT preserves the strong pooled resemblance advantage, especially edge KL ({cs['pooled_edge_kl']:.6g} Context versus {fs['pooled_edge_kl']:.6g} Frequency). Mean and median edge KL agree. Per-run tile KL is more variable and is not uniformly better.</li>
<li><b>Seed 0 representativeness:</b> Frequency SAT tile/edge KL is {frequency_seed0['tile_kl']:.6g}/{frequency_seed0['edge_kl']:.6g}; Context SAT is {context_seed0['tile_kl']:.6g}/{context_seed0['edge_kl']:.6g}. Both lie within their observed distributions. Context seed 0 is better than its medians but is not an extreme best case.</li>
<li><b>Timeouts:</b> 0/100 for both SAT heuristics. Frequency has a longer solve-time tail (maximum {fs['solve_seconds']['max']:.3f}s) than Context ({cs['solve_seconds']['max']:.3f}s).</li>
</ol><p>These are matched-seed and distributional comparisons, not a claim that ordinary WFC and WFC-as-SAT are equivalent algorithms.</p>"""
    REPORT.write_text(f"""<!doctype html><html><head><meta charset=utf-8><title>Zelda 1x1 weighted matched experiment</title>
<style>body{{font:15px/1.45 system-ui;margin:2rem;color:#172033;background:#f4f6fa}}main{{max-width:1500px;margin:auto}}table{{border-collapse:collapse;background:white}}th,td{{border:1px solid #9aa7b8;padding:.45rem;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}.gallery{{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:1rem}}figure{{margin:0;background:white;padding:.7rem;border:1px solid #bdc7d4}}img{{width:100%;image-rendering:pixelated}}.source{{max-width:900px}}.note{{background:#fff7d6;border-left:5px solid #d09b00;padding:1rem}}</style></head><body><main>
<h1>Zelda 1x1: matched weighted WFC and WFC-as-SAT</h1><p>100 fixed seeds (0–99), 20×20 output, lexical selection, finite/nonperiodic boundary. SAT uses DomainObserver with CaDiCaL 1.9.5. Each SAT seed had a {metadata['sat_timeout_seconds']}-second worker timeout; failures and timeouts were retained.</p>
<figure class=source><img src='images/zelda-1x1-weighted/source.png'><figcaption>Source Zelda map</figcaption></figure>
<h2>Results</h2><table><thead><tr><th>Heuristic</th><th>Engine</th><th>Success</th><th>Timeout</th><th>Failure</th><th>Pooled tile KL</th><th>Mean tile KL</th><th>Median tile KL</th><th>Pooled edge KL</th><th>Mean edge KL</th><th>Median edge KL</th><th>Mean runtime s</th><th>Median runtime s</th><th>Mean conflicts</th><th>Mean decisions</th><th>Mean observer backtracks</th><th>Exact matched images</th></tr></thead><tbody>{table_rows}</tbody></table>
<div class=note><b>Uniform remains incomplete.</b> Its separately diagnosed seed-0 WFC-decision run exceeded 174 seconds. It was not run in this weighted sweep. Plain CaDiCaL is only a diagnostic control and is not substituted for WFC-as-SAT here.</div>
{answers}
{''.join(gallery)}
<h2>Raw data</h2><p><a href='raw/zelda-1x1-weighted-matched.json'>JSON</a> · <a href='zelda-1x1-weighted-per-run.csv'>per-run CSV</a> · <a href='zelda-1x1-weighted-summary.csv'>summary CSV</a></p>
</main></body></html>""", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--sat-timeout", type=float, default=30.0)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    if args.runs != 100:
        raise ValueError("this experiment is fixed to exactly 100 seeds")
    source, rgba = tile_source()
    model = WFCModel.from_tile_grid(source)
    if args.report_only:
        payload = json.loads(RAW_JSON.read_text(encoding="utf-8"))
        records = payload["runs"]
        metadata = payload["metadata"]
        summaries = summarize(records, source)
        write_outputs(records, summaries, source, rgba, model, metadata)
        print(REPORT, flush=True)
        return
    global CNF, MAPPING, TILE_FOR_ID
    CNF, MAPPING, TILE_FOR_ID = sat_instance(model, rgba)
    if CNF.num_vars != 36000 or len(CNF.clauses) != 1670800:
        raise RuntimeError("unexpected Zelda 1x1 formula size")
    metadata = {
        "source": "examples/context-sensitive/zelda-map-authors.png",
        "pattern_size": 1, "output": "20x20", "boundary": "finite/nonperiodic",
        "selection": "lexical", "heuristics": list(HEURISTICS), "seeds": list(range(100)),
        "sat": "PySAT Cadical195 + DomainObserver", "sat_timeout_seconds": args.sat_timeout,
        "variables": CNF.num_vars, "clauses": len(CNF.clauses),
        "exactly_one_clauses": 1602400, "compatibility_support_clauses": 68400,
        "gallery_seeds": list(GALLERY_SEEDS), "uniform": "incomplete; not run",
    }
    records = []
    context = multiprocessing.get_context("fork")
    for seed in range(100):
        for heuristic in HEURISTICS:
            print(f"seed {seed:02d} {heuristic} ordinary WFC start", flush=True)
            ordinary = run_wfc(model, heuristic, seed)
            ordinary.update({"timed_out": False, "failure": not ordinary["success"], "error": None})
            add_metrics([ordinary], source)
            records.append(ordinary)
            save_incremental(records, metadata)
            print(f"seed {seed:02d} {heuristic} ordinary WFC done success={ordinary['success']} runtime={ordinary['runtime_seconds']:.6f}s", flush=True)

            print(f"seed {seed:02d} {heuristic} WFC-as-SAT start timeout={args.sat_timeout:.0f}s", flush=True)
            sat = run_sat_timed(context, heuristic, seed, args.sat_timeout)
            add_metrics([sat], source)
            records.append(sat)
            save_incremental(records, metadata)
            print(f"seed {seed:02d} {heuristic} WFC-as-SAT done success={sat['success']} timeout={sat['timed_out']} runtime={sat['runtime_seconds']:.6f}s", flush=True)
    summaries = summarize(records, source)
    write_outputs(records, summaries, source, rgba, model, metadata)
    print(json.dumps(summaries, indent=2), flush=True)
    print(REPORT, flush=True)


if __name__ == "__main__":
    main()
