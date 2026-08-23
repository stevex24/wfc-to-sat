"""Generate the validated Simple Knot N=3/N=4 reports and heat maps."""

from pathlib import Path

from tests._pattern_oracle import (
    independently_pattern_id_grid,
    validate_patterns_and_overlaps,
)
from tests._pattern_report import (
    build_comparison_report,
    build_pattern_id_grid,
    build_pattern_report,
    write_heat_map_png,
)
from wfc_to_sat.patterns import extract_patterns, load_image_grid


ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "examples" / "simple-knot.png"
PER_SIZE_REPORTS = {
    3: ROOT / "pattern-report.html",
    4: ROOT / "simple-knot-n4-report.html",
}
COMPARISON_REPORT = ROOT / "simple-knot-pattern-comparison.html"


def main():
    grid = load_image_grid(IMAGE)
    validated_cases = []
    for pattern_size in (3, 4):
        validation = validate_patterns_and_overlaps(grid, pattern_size)
        patterns = extract_patterns(grid, pattern_size)
        id_grid = build_pattern_id_grid(grid, pattern_size, patterns)
        oracle_grid = independently_pattern_id_grid(grid, pattern_size, patterns)
        if id_grid != oracle_grid:
            raise AssertionError(f"N={pattern_size} heat map differs from oracle")

        PER_SIZE_REPORTS[pattern_size].write_text(
            build_pattern_report(((IMAGE.name, grid, pattern_size),)),
            encoding="utf-8",
        )
        heat_map_path = ROOT / f"simple-knot-n{pattern_size}-heat-map.png"
        write_heat_map_png(id_grid, heat_map_path)
        validated_cases.append((pattern_size, validation))
        print(
            f"N={pattern_size}: windows={validation.windows}, "
            f"unique={validation.unique_patterns}, "
            f"duplicates={validation.duplicate_occurrences}, validation=PASS"
        )
        print(f"HTML report: {PER_SIZE_REPORTS[pattern_size].name}")
        print(f"PNG heat map: {heat_map_path.name}")

    COMPARISON_REPORT.write_text(
        build_comparison_report(IMAGE, grid, validated_cases),
        encoding="utf-8",
    )
    print(f"Comparison report: {COMPARISON_REPORT.name}")
    print("Overall: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
