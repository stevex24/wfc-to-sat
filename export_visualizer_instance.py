#!/usr/bin/env python3
"""Export an image-derived WFC instance for the CDCL trace visualizer."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Iterable

from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import extract_patterns_from_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--pattern-size", type=int, default=3)
    parser.add_argument("--width", type=int, default=8)
    parser.add_argument("--height", type=int, default=8)
    parser.add_argument("--output-prefix", type=Path, required=True)
    return parser


def export_instance(
    image: Path,
    pattern_size: int,
    width: int,
    height: int,
    output_prefix: Path,
) -> tuple[Path, Path, int, int]:
    if pattern_size <= 0:
        raise ValueError("pattern size must be positive")
    if width <= 0 or height <= 0:
        raise ValueError("output dimensions must be positive")

    patterns = extract_patterns_from_image(image, pattern_size)
    if not patterns:
        raise ValueError("pattern size is larger than the source image")

    allowed = build_compatibility(patterns)
    cnf = patterns_to_cnf(patterns, allowed, width=width, height=height)

    cnf_path = Path(f"{output_prefix}.cnf")
    mapping_path = Path(f"{output_prefix}.map.json")
    cnf_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    cnf_path.write_text(cnf.dimacs(), encoding="ascii")

    mapping = {
        "grid": {"width": width, "height": height},
        "patterns": [
            {
                "id": pattern.id,
                "frequency": pattern.frequency,
                "width": pattern_size,
                "height": pattern_size,
                "rgba": base64.b64encode(
                    bytes(
                        component
                        for row in pattern.rows
                        for pixel in row
                        for component in pixel
                    )
                ).decode("ascii"),
            }
            for pattern in patterns
        ],
        "variables": [
            {
                "var": variable,
                "x": x,
                "y": y,
                "pattern_id": pattern_id,
            }
            for variable, (x, y, pattern_id) in sorted(cnf.name_map.items())
        ],
        "compatibility": {
            direction: {
                str(pattern_id): compatible_patterns
                for pattern_id, compatible_patterns in table.items()
            }
            for direction, table in allowed.items()
        },
    }
    mapping_path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    return cnf_path, mapping_path, len(patterns), cnf.num_vars


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cnf_path, mapping_path, pattern_count, variable_count = export_instance(
            image=args.image,
            pattern_size=args.pattern_size,
            width=args.width,
            height=args.height,
            output_prefix=args.output_prefix,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"export_visualizer_instance: {error}")
        return 2

    print(f"Extracted patterns: {pattern_count}")
    print(f"Placement variables: {variable_count}")
    print(f"Wrote {cnf_path}")
    print(f"Wrote {mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
