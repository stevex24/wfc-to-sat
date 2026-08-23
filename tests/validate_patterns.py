"""Run the independent pattern extraction and overlap validator.

Run from the repository root with either:

    python3 -m tests.validate_patterns
    python3 tests/validate_patterns.py
"""

import argparse
from pathlib import Path
import sys


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._pattern_oracle import validate_patterns_and_overlaps
from tests._pattern_report import build_pattern_report
from wfc_to_sat.patterns import load_image_grid


CASES = (
    (
        "repeated checkerboard, N=2",
        ["ABABA", "BABAB", "ABABA", "BABAB"],
        2,
    ),
    (
        "rectangular mixed grid, N=2",
        ["ABCD", "BCDA", "CABC", "ABCD"],
        2,
    ),
    (
        "duplicate single-cell patterns, N=1",
        ["AABA", "AABA"],
        1,
    ),
    (
        "repeated three-cell windows, N=3",
        ["ABABA", "BABAB", "ABABA", "BABAB", "ABABA"],
        3,
    ),
)


def _arguments(argv=None):
    """Parse command-line reporting options."""
    parser = argparse.ArgumentParser(
        description="Validate pattern extraction and overlap compatibility."
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="HTML_PATH",
        help="write a self-contained illustrated HTML report",
    )
    parser.add_argument(
        "--image",
        type=Path,
        metavar="IMAGE_PATH",
        help="validate pattern extraction from a PNG or JPEG image",
    )
    parser.add_argument(
        "--pattern-size",
        type=int,
        default=2,
        metavar="N",
        help="square pattern size for --image (default: 2)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    """Validate all fixtures and report duplicate and overlap counts."""
    arguments = _arguments(argv)
    cases = CASES
    if arguments.image:
        image_grid = load_image_grid(arguments.image)
        cases = ((arguments.image.name, image_grid, arguments.pattern_size),)

    print("Pattern extraction and overlap validation")
    for name, grid, pattern_size in cases:
        report = validate_patterns_and_overlaps(grid, pattern_size)
        print(
            f"{name}: windows={report.windows}, "
            f"unique patterns={report.unique_patterns}, "
            f"duplicate occurrences={report.duplicate_occurrences}, "
            f"right pairs={report.right_pairs}, down pairs={report.down_pairs}, "
            "extraction identical=yes, overlaps identical=yes"
        )
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(build_pattern_report(cases), encoding="utf-8")
        print(f"HTML report: {arguments.report}")
    print("Overall: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
