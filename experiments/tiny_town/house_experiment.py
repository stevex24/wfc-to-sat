#!/usr/bin/env python3
"""Compile, solve, and render the Kenney Tiny Town house SAT experiment."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import random
import sys

from PIL import Image, ImageDraw
from pysat.solvers import Cadical195

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.tiny_town.fetch_assets import ensure_assets
from wfc_to_sat.house_structure import HouseCnf, TileManifest

HERE = Path(__file__).resolve().parent


def compile_instance(width: int, height: int, minimum: int, maximum: int, output: Path) -> tuple[HouseCnf, dict]:
    manifest = TileManifest.load(HERE / "manifest.json")
    cnf = HouseCnf(width, height, manifest, counter_limit=max(maximum + 1, 2)).build(minimum, maximum)
    assets = ensure_assets()
    patterns = []
    for tile in cnf.tiles:
        image = Image.open(assets / f"tile_{tile:04d}.png").convert("RGBA")
        patterns.append({"id": tile, "frequency": 1, "width": 16, "height": 16,
                         "rgba": base64.b64encode(image.tobytes()).decode("ascii"),
                         "role": manifest.tile_roles[tile]})
    mapping = {
        "grid": {"width": width, "height": height},
        "patterns": patterns,
        "variables": [{"var": cnf.assign(x, y, tile), "x": x, "y": y, "pattern_id": tile}
                      for y in range(height) for x in range(width) for tile in cnf.tiles],
        "structural": cnf.structural_mapping(),
        "house_bounds": {"min": minimum, "max": maximum},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{output}.cnf").write_text(cnf.dimacs(), encoding="ascii")
    Path(f"{output}.map.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    return cnf, mapping


def solve_instance(cnf: HouseCnf, exact: int | None, seed: int) -> list[int] | None:
    assumptions: list[int] = []
    if exact is not None:
        if exact >= cnf.counter_limit:
            raise ValueError(f"exact count exceeds compiled capacity {cnf.counter_limit - 1}")
        if exact:
            assumptions.append(cnf.counter(cnf.cells, exact))
        assumptions.append(-cnf.counter(cnf.cells, exact + 1))
    clauses = list(cnf.clauses)
    random.Random(seed).shuffle(clauses)
    with Cadical195(bootstrap_with=clauses) as solver:
        return solver.get_model() if solver.solve(assumptions=assumptions) else None


def decode(cnf: HouseCnf, model: list[int]) -> tuple[list[list[int]], list[list[bool]], list[tuple[int, int]]]:
    positive = {lit for lit in model if lit > 0}
    tiles = [[next(tile for tile in cnf.tiles if cnf.assign(x, y, tile) in positive)
              for x in range(cnf.width)] for y in range(cnf.height)]
    inside = [[cnf.inside(x, y) in positive for x in range(cnf.width)] for y in range(cnf.height)]
    anchors = [(x, y) for y in range(cnf.height) for x in range(cnf.width) if cnf.anchor(x, y) in positive]
    return tiles, inside, anchors


def render(cnf: HouseCnf, model: list[int], destination: Path) -> None:
    assets = ensure_assets()
    tiles, inside, anchors = decode(cnf, model)
    scale, margin = 3, 24
    image = Image.new("RGBA", (cnf.width * 16 * scale, cnf.height * 16 * scale + margin), "#17202a")
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            sprite = Image.open(assets / f"tile_{tile:04d}.png").convert("RGBA").resize((16 * scale, 16 * scale), Image.NEAREST)
            image.alpha_composite(sprite, (x * 16 * scale, y * 16 * scale))
    draw = ImageDraw.Draw(image)
    for x, y in anchors:
        draw.rectangle((x * 16 * scale + 2, y * 16 * scale + 2, (x + 1) * 16 * scale - 3, (y + 1) * 16 * scale - 3), outline="#ffe66d", width=2)
    draw.text((6, cnf.height * 16 * scale + 5), f"houses: {len(anchors)}  (yellow = anchor)", fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(destination)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--width", type=int, default=16)
    p.add_argument("--height", type=int, default=12)
    p.add_argument("--min-houses", type=int, default=2)
    p.add_argument("--max-houses", type=int, default=5)
    p.add_argument("--exact-houses", type=int)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output-prefix", type=Path, default=ROOT / "local-generated-output/tiny-town/houses")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.exact_houses is not None and not args.min_houses <= args.exact_houses <= args.max_houses:
        print("exact count must be within compiled min/max bounds", file=sys.stderr)
        return 2
    try:
        cnf, _ = compile_instance(args.width, args.height, args.min_houses, args.max_houses, args.output_prefix)
        model = solve_instance(cnf, args.exact_houses, args.seed)
    except (OSError, ValueError) as error:
        print(f"house_experiment: {error}", file=sys.stderr)
        return 2
    result_path = Path(f"{args.output_prefix}.result.json")
    if model is None:
        result_path.write_text(json.dumps({"status": "UNSAT"}, indent=2) + "\n", encoding="utf-8")
        print("UNSAT")
        return 1
    tiles, inside, anchors = decode(cnf, model)
    result_path.write_text(json.dumps({"status": "SAT", "houses": len(anchors), "anchors": anchors,
                                      "tiles": tiles, "in": inside}, indent=2) + "\n", encoding="utf-8")
    png = Path(f"{args.output_prefix}.png")
    render(cnf, model, png)
    print(f"SAT: {len(anchors)} houses; wrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
