import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from tests._pattern_oracle import (
    independently_pattern_id_grid,
    validate_patterns_and_overlaps,
)
from tests._pattern_report import build_pattern_id_grid
from tests.validate_patterns import CASES
from tests.validate_patterns import main
from wfc_to_sat.patterns import (
    extract_pattern_occurrence_grid,
    extract_patterns,
    extract_patterns_from_image,
    load_image_grid,
)


class PatternSemanticTests(unittest.TestCase):
    def test_nonwrapped_extraction_remains_the_default(self):
        grid = ["ABC", "DEF", "GHI"]
        self.assertEqual(extract_patterns(grid, 2), extract_patterns(grid, 2, extraction="nonwrapped"))
        self.assertEqual(sum(p.frequency for p in extract_patterns(grid, 2)), 4)

    def test_periodic_extraction_wraps_both_axes_and_preserves_multiplicity(self):
        grid = ["AB", "CD"]
        patterns, occurrences = extract_pattern_occurrence_grid(
            grid, 2, extraction="periodic"
        )
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(tuple(map(len, occurrences)), (2, 2))
        self.assertEqual(sum(pattern.frequency for pattern in patterns), 4)
        self.assertEqual(
            {pattern.rows for pattern in patterns},
            {
                (("A", "B"), ("C", "D")),
                (("B", "A"), ("D", "C")),
                (("C", "D"), ("A", "B")),
                (("D", "C"), ("B", "A")),
            },
        )

    def test_periodic_corner_windows_have_correct_overlap_compatibility(self):
        from wfc_to_sat.compatibility import build_compatibility, overlaps_down, overlaps_right

        patterns = extract_patterns(["AB", "CD"], 2, extraction="periodic")
        allowed = build_compatibility(patterns)
        for left in patterns:
            self.assertEqual(
                allowed["right"][left.id],
                [right.id for right in patterns if overlaps_right(left, right)],
            )
            self.assertEqual(
                allowed["down"][left.id],
                [below.id for below in patterns if overlaps_down(left, below)],
            )

    def test_periodic_occurrences_reconstruct_the_source_from_pattern_origins(self):
        grid = ["ABC", "DEF"]
        patterns, occurrences = extract_pattern_occurrence_grid(
            grid, 2, extraction="periodic"
        )
        by_id = {pattern.id: pattern for pattern in patterns}
        reconstructed = tuple(
            tuple(by_id[occurrences[y][x]].rows[0][0] for x in range(3))
            for y in range(2)
        )
        self.assertEqual(reconstructed, tuple(tuple(row) for row in grid))

    def test_extraction_and_overlaps_match_independent_oracles(self):
        for name, grid, pattern_size in CASES:
            with self.subTest(case=name):
                report = validate_patterns_and_overlaps(grid, pattern_size)
                self.assertTrue(report.extraction_identical)
                self.assertTrue(report.overlaps_identical)

    def test_repeated_windows_are_counted_with_multiplicity(self):
        report = validate_patterns_and_overlaps(
            ["ABABA", "BABAB", "ABABA", "BABAB"],
            2,
        )

        self.assertEqual(report.windows, 12)
        self.assertEqual(report.unique_patterns, 2)
        self.assertEqual(report.duplicate_occurrences, 10)

    def test_heat_map_ids_and_frequencies_match_independent_oracle(self):
        grid = ["ABABA", "BABAB", "ABABA", "BABAB"]
        patterns = extract_patterns(grid, 2)
        heat_map = build_pattern_id_grid(grid, 2, patterns)
        oracle_heat_map = independently_pattern_id_grid(grid, 2, patterns)

        self.assertEqual(heat_map, oracle_heat_map)
        self.assertEqual(heat_map[0][0], heat_map[0][2])
        self.assertEqual(heat_map[0][1], heat_map[0][3])
        self.assertEqual(sum(pattern.frequency for pattern in patterns), 12)

    def test_illustrated_html_report_can_be_written(self):
        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "patterns.html"
            self.assertEqual(main(["--report", str(report_path)]), 0)
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("<svg", report)
        self.assertIn("Frequency: <strong>6</strong>", report)
        self.assertIn("Observed frequency:", report)
        self.assertIn("Pattern extraction and overlap report", report)

    def test_comparison_report_has_labelled_source_window_explorer(self):
        from tests._pattern_report import build_comparison_report

        grid = load_image_grid(Path("examples/simple-knot.png"))
        validated_cases = [
            (size, validate_patterns_and_overlaps(grid, size))
            for size in (3, 4)
        ]
        report = build_comparison_report(
            Path("examples/simple-knot.png"), grid, validated_cases
        )

        self.assertIn('id="source-grid"', report)
        self.assertIn('id="extraction-window"', report)
        self.assertIn('<option value="3">3</option>', report)
        self.assertIn('<option value="4">4</option>', report)
        self.assertIn("left-to-right, then top-to-bottom", report)
        self.assertIn("Origin (", report)
        self.assertIn("Pattern ${origin.id}", report)
        self.assertIn("Frequency ${origin.frequency}", report)
        self.assertEqual(report.count('class="source-pixel"'), 121)
        self.assertEqual(report.count('class="axis-label"'), 22)

    def test_png_image_patterns_preserve_pixel_colors_and_frequencies(self):
        from PIL import Image

        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "checker.png"
            report_path = Path(directory) / "report.html"
            image = Image.new("RGB", (3, 3))
            image.putdata(
                [
                    (255, 0, 0), (0, 0, 255), (255, 0, 0),
                    (0, 0, 255), (255, 0, 0), (0, 0, 255),
                    (255, 0, 0), (0, 0, 255), (255, 0, 0),
                ]
            )
            image.save(image_path)

            patterns = extract_patterns_from_image(image_path, 2)
            self.assertEqual(sorted(pattern.frequency for pattern in patterns), [2, 2])
            self.assertEqual(patterns[0].rows[0][0], (255, 0, 0, 255))
            self.assertEqual(
                main(
                    [
                        "--image", str(image_path),
                        "--pattern-size", "2",
                        "--report", str(report_path),
                    ]
                ),
                0,
            )
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("rgba(255,0,0,1.000)", report)
        self.assertIn("checker.png", report)

    def test_jpeg_image_is_loaded_as_rgba_cells(self):
        from PIL import Image

        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "solid.jpg"
            Image.new("RGB", (3, 3), (20, 40, 60)).save(
                image_path,
                quality=100,
                subsampling=0,
            )
            grid = load_image_grid(image_path)
            patterns = extract_patterns_from_image(image_path, 2)

        self.assertEqual(len(grid), 3)
        self.assertEqual(len(grid[0]), 3)
        self.assertEqual(len(grid[0][0]), 4)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].frequency, 4)


if __name__ == "__main__":
    unittest.main()
