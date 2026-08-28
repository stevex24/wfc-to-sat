#!/usr/bin/env python3
"""Paper-style Zelda 1x1 experiment using the authors' 16x16 tile map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.context_sensitive.core_experiment import (
    add_metrics, run_sat, run_wfc, summaries,
)
from observer import DomainObserver
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.ordinary_wfc import WFCModel
from wfc_to_sat.patterns import Pattern

SOURCE = ROOT / "examples/context-sensitive/zelda-map-authors.png"
OUT = ROOT / "context-sensitive-results/detailed-comparison/raw/zelda-1x1.json"
DECISIONS = ("uniform", "frequency", "context")


def tile_source(path=SOURCE, tile_size=16):
    image = Image.open(path).convert("RGBA")
    if image.width % tile_size or image.height % tile_size:
        raise ValueError("Zelda source dimensions are not divisible by 16")
    ids, tiles, rows = {}, [], []
    for y in range(0, image.height, tile_size):
        row = []
        for x in range(0, image.width, tile_size):
            rgba = image.crop((x, y, x + tile_size, y + tile_size)).tobytes()
            if rgba not in ids:
                ids[rgba] = len(tiles)
                tiles.append(rgba)
            row.append(chr(0x1000 + ids[rgba]))
        rows.append("".join(row))
    return tuple(rows), tuple(tiles)


def sat_instance(model, tile_rgba, width=20, height=20):
    tile_id = {tile: i for i, tile in enumerate(model.tiles)}
    patterns = [Pattern(tile_id[tile], ((tile,),), model.frequencies[tile]) for tile in model.tiles]
    allowed = {
        "right": {tile_id[t]: [tile_id[v] for v in model.adjacency["east"][t]] for t in model.tiles},
        "down": {tile_id[t]: [tile_id[v] for v in model.adjacency["south"][t]] for t in model.tiles},
    }
    cnf = patterns_to_cnf(
        patterns, allowed, width, height, adjacency_encoding="support"
    )
    specs = tuple(
        PatternSpec(tile_id[t], model.frequencies[t], 16, 16, tile_rgba[tile_id[t]])
        for t in model.tiles
    )
    placements = tuple(
        Placement(var, x, y, pattern_id)
        for var, (x, y, pattern_id) in sorted(cnf.name_map.items())
    )
    mapping = MappingSpec(
        width, height, specs, placements, allowed,
        tuple(tuple(tile_id[t] for t in row) for row in model.context_frequencies.source_grid),
    )
    mapping.validate(num_vars=cnf.num_vars)
    return cnf, mapping, {i: tile for tile, i in tile_id.items()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--engine", choices=("ordinary", "all"), default="all")
    args = parser.parse_args(argv)
    source, rgba = tile_source()
    model = WFCModel.from_tile_grid(source)
    if len(model.tiles) != 90:
        raise RuntimeError(f"expected the paper's 90 Zelda tiles, found {len(model.tiles)}")
    if args.engine == "all":
        cnf, mapping, tile_for_id = sat_instance(model, rgba)
    records = []
    for seed in range(args.runs):
        for decision in DECISIONS:
            records.append(run_wfc(model, decision, seed))
            if args.engine == "all":
                records.append(run_sat(cnf, mapping, tile_for_id, decision, seed))
    if args.engine == "all":
        records.append(run_sat(cnf, mapping, tile_for_id, "solver", 0))
    add_metrics(records, source)
    payload = {
        "metadata": {
            "repository": "https://github.com/stevex24/wfc-to-sat",
            "branch": "spec-completion-report",
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "input": str(SOURCE.relative_to(ROOT)),
            "input_sha256": "c572b1c3d8ce7b05609f28a7dae4e0697232a2e7fe07e4c99dd93e9811693ed3",
            "tile_pixels": "16x16", "pattern_size": 1, "output": "20x20",
            "source_grid": "256x88 tiles", "unique_tiles": 90,
            "source_extraction": "nonwrapped 1x1 (wrapping is immaterial at N=1)",
            "generated_output_boundary": "finite/nonperiodic",
            "selection": "lexical", "seeds": list(range(args.runs)),
            "python": platform.python_version(),
            "sat_solver": "CaDiCaL 1.9.5 via PySAT",
            "sat_adjacency_encoding": "support clauses (logically equivalent to default forbidden pairs)",
            "contradiction_policy": {"ordinary_wfc": "stop", "sat": "CDCL"},
        },
        "runs": records,
        "summary": summaries(records, source),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "records": len(records)}, indent=2))


if __name__ == "__main__":
    main()
