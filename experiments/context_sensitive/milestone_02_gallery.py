#!/usr/bin/env python3
"""Generate standalone ordinary-WFC Stick outputs and an HTML gallery."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel


SOURCE_PATH = ROOT / "examples" / "context-sensitive" / "stick.txt"
OUTPUT_DIR = ROOT / "context-sensitive-results" / "milestone-02"
SEEDS = (0, 1, 2, 3, 4)
DECISIONS = ("uniform", "frequency", "context")


def read_source():
    return tuple(tuple(row) for row in SOURCE_PATH.read_text().splitlines())


def render_grid(rows, css_class="output-grid"):
    width = len(rows[0])
    cells = "".join(
        f'<span class="tile tile-{tile or "blank"}" title="({x},{y}) = {tile}"></span>'
        for y, row in enumerate(rows)
        for x, tile in enumerate(row)
    )
    return f'<div class="{css_class}" style="--width:{width}">{cells}</div>'


def generate():
    source = read_source()
    model = WFCModel.from_tile_grid(source)
    results = []
    by_key = {}
    for seed in SEEDS:
        for decision in DECISIONS:
            result = OrdinaryWFC(
                model,
                20,
                20,
                selection="lexical",
                decision=decision,
                seed=seed,
            ).run()
            record = {
                "engine": "standalone ordinary WFC",
                "selection": result.selection,
                "decision": result.decision,
                "contradiction_policy": result.contradiction_policy,
                "seed": result.seed,
                "width": result.width,
                "height": result.height,
                "success": result.success,
                "contradictions": result.contradictions,
                "attempts": result.attempts,
                "restarts": result.restarts,
                "observations": result.observations,
                "output": ["".join(tile or "?" for tile in row) for row in result.output],
            }
            results.append(record)
            by_key[(decision, seed)] = result

    cards = []
    for seed in SEEDS:
        cards.append(
            '<article class="card source-card">'
            '<h3>Source</h3>'
            f'{render_grid(source, "source-grid")}<p>7×7 paper Stick<br>44 black, 5 white</p></article>'
        )
        for decision in DECISIONS:
            result = by_key[(decision, seed)]
            cards.append(
                '<article class="card">'
                f'<h3>{decision.title()} WFC</h3>{render_grid(result.output)}'
                f'<p>selection: lexical<br>decision: {decision}<br>seed: {seed}<br>'
                f'output: 20×20<br>success: {str(result.success).lower()}<br>'
                f'contradictions: {result.contradictions}<br>attempts: {result.attempts}<br>'
                f'restarts: {result.restarts}<br>contradiction policy: stop</p></article>'
            )

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Milestone 02 ordinary-WFC Stick gallery</title><style>
body{{font:15px/1.4 system-ui,sans-serif;margin:2rem;background:#f4f6fa;color:#172033}} h1{{margin-bottom:.3rem}}
.notice{{background:#dbeafe;border-left:5px solid #2563eb;padding:1rem;max-width:1100px;font-weight:650}}
.gallery{{display:grid;grid-template-columns:repeat(4,minmax(245px,1fr));gap:1rem;align-items:start;min-width:1040px}}
.card{{background:white;border:1px solid #cbd5e1;border-radius:8px;padding:.8rem;box-shadow:0 2px 8px #0f172a12}}
.card h3{{margin:.1rem 0 .6rem}} .card p{{font-family:ui-monospace,monospace;font-size:12px;margin:.65rem 0 0}}
.output-grid,.source-grid{{display:grid;grid-template-columns:repeat(var(--width),1fr);gap:1px;background:#64748b;border:2px solid #334155;aspect-ratio:1}}
.tile{{display:block;min-width:0;background:#18181b}} .tile-W{{background:#fff}} .tile-blank{{background:#f43f5e}}
.source-grid{{width:210px;height:210px;margin:auto}} .source-grid .tile{{min-width:28px}}
.legend{{display:flex;gap:1rem;align-items:center}} .swatch{{display:inline-block;width:1rem;height:1rem;border:1px solid #64748b;vertical-align:-.15rem}}
@media(max-width:1100px){{body{{overflow-x:auto}}}}
</style></head><body><h1>Milestone 02: standalone ordinary-WFC Stick outputs</h1>
<p class="notice">These are real outputs from the new standalone ordinary-WFC reference engine. SAT/CDCL is not invoked.</p>
<p>Uncurated fixed seeds 0–4. Every condition uses lexical top-left-to-bottom-right selection and a 20×20 output. No automatic restart or backtracking is used.</p>
<p class="legend"><span><i class="swatch tile-B"></i> black (B)</span><span><i class="swatch tile-W"></i> white (W)</span><span><i class="swatch tile-blank"></i> contradiction/blank</span></p>
<div class="gallery">{''.join(cards)}</div></body></html>"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "runs.json").write_text(json.dumps(results, indent=2) + "\n")
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    return results


def main():
    results = generate()
    for decision in DECISIONS:
        subset = [item for item in results if item["decision"] == decision]
        print(
            f"{decision}: success={sum(item['success'] for item in subset)}/{len(subset)}, "
            f"contradictions={sum(item['contradictions'] for item in subset)}, "
            f"restarts={sum(item['restarts'] for item in subset)}"
        )
    print(OUTPUT_DIR / "index.html")


if __name__ == "__main__":
    main()
