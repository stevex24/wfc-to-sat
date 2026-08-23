import unittest
from pathlib import Path

from wfc_to_sat.context_frequency import (
    UNK,
    ContextFrequencies,
    masked_contexts,
)


# This checkerboard is deliberately small enough for every expectation below
# to be derived directly from coordinates, without a second implementation.
SOURCE = (
    ("A", "B", "A"),
    ("B", "A", "B"),
    ("A", "B", "A"),
)


class ContextFrequencyTests(unittest.TestCase):
    def setUp(self):
        self.table = ContextFrequencies(SOURCE)

    def test_source_frequency_counts_duplicate_occurrences(self):
        self.assertEqual(self.table.tiles, ("A", "B"))
        self.assertEqual(self.table.tile_frequency("A"), 5)
        self.assertEqual(self.table.tile_frequency("B"), 4)

    def test_complete_contexts_include_boundaries_in_north_east_south_west_order(self):
        self.assertEqual(
            self.table.complete_contexts,
            (
                ("A", (UNK, "B", "B", UNK)),
                ("B", (UNK, "A", "A", "A")),
                ("A", (UNK, UNK, "B", "B")),
                ("B", ("A", "A", "A", UNK)),
                ("A", ("B", "B", "B", "B")),
                ("B", ("A", UNK, "A", "A")),
                ("A", ("B", "B", UNK, UNK)),
                ("B", ("A", "A", UNK, "A")),
                ("A", ("B", UNK, UNK, "B")),
            ),
        )

    def test_masked_context_variants_are_unique_and_deterministic(self):
        complete = ("N", "E", "S", "W")
        first = masked_contexts(complete)
        self.assertEqual(first, masked_contexts(complete))
        self.assertEqual(len(first), 16)
        self.assertEqual(len(set(first)), 16)
        self.assertIn(("N", UNK, "S", UNK), first)
        self.assertIn((UNK, UNK, UNK, UNK), first)

        boundary = (UNK, "E", "S", UNK)
        self.assertEqual(len(masked_contexts(boundary)), 4)
        self.assertEqual(len(set(masked_contexts(boundary))), 4)
        one_boundary = (UNK, "E", "S", "W")
        self.assertEqual(len(masked_contexts(one_boundary)), 8)
        self.assertEqual(len(set(masked_contexts(one_boundary))), 8)

    def test_exact_complete_and_masked_frequencies(self):
        corner_context = (UNK, "B", "B", UNK)
        self.assertEqual(self.table.frequency("A", corner_context), 2)
        self.assertEqual(self.table.frequency("B", corner_context), 0)
        self.assertEqual(self.table.frequency("A", ("B", "B", "B", "B")), 1)
        self.assertEqual(self.table.frequency("B", (UNK, "A", "A", "A")), 1)

        partially_masked = (UNK, "B", "B", UNK)
        self.assertEqual(self.table.frequency("A", partially_masked), 2)
        self.assertEqual(
            self.table.frequency("A", (UNK, UNK, UNK, UNK)),
            5,
        )
        self.assertEqual(
            self.table.frequency("B", (UNK, UNK, UNK, UNK)),
            4,
        )

    def test_candidate_weight_lookup_and_unseen_detection(self):
        known = ("B", "B", "B", "B")
        self.assertTrue(self.table.context_was_seen(known))
        lookup = self.table.candidate_weights(("A", "B"), known)
        self.assertEqual(lookup.weights, (1, 0))
        self.assertFalse(lookup.used_frequency_fallback)

        unseen = ("A", "A", "A", "A")
        self.assertFalse(self.table.context_was_seen(unseen))
        lookup = self.table.candidate_weights(("A", "B"), unseen)
        self.assertEqual(lookup.weights, (5, 4))
        self.assertTrue(lookup.used_frequency_fallback)

    def test_context_known_for_other_tiles_falls_back_for_legal_subset(self):
        context = ("B", "B", "B", "B")
        self.assertTrue(self.table.context_was_seen(context))
        lookup = self.table.candidate_weights(("B",), context)
        self.assertEqual(lookup.weights, (4,))
        self.assertTrue(lookup.used_frequency_fallback)

    def test_preprocessing_results_are_deterministic(self):
        other = ContextFrequencies(SOURCE)
        self.assertEqual(self.table.tiles, other.tiles)
        self.assertEqual(self.table.complete_contexts, other.complete_contexts)
        for tile in self.table.tiles:
            for _, context in self.table.complete_contexts:
                self.assertEqual(
                    self.table.frequency(tile, context),
                    other.frequency(tile, context),
                )

    def test_rejects_invalid_sources_and_reserved_marker(self):
        with self.assertRaises(ValueError):
            ContextFrequencies(())
        with self.assertRaises(ValueError):
            ContextFrequencies((("A",), ("A", "B")))
        with self.assertRaises(ValueError):
            ContextFrequencies(((UNK,),))

    def test_paper_stick_source_has_five_white_cells_and_expected_all_unk_counts(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "context-sensitive"
            / "stick.txt"
        )
        source = tuple(tuple(row) for row in path.read_text().splitlines())
        table = ContextFrequencies(source)
        all_unknown = (UNK, UNK, UNK, UNK)

        self.assertEqual((table.width, table.height), (7, 7))
        self.assertEqual(table.tile_frequency("B"), 44)
        self.assertEqual(table.tile_frequency("W"), 5)
        self.assertEqual(table.frequency("B", all_unknown), 44)
        self.assertEqual(table.frequency("W", all_unknown), 5)
        self.assertEqual(tuple(source[y][3] for y in range(7)), tuple("BWWWWWB"))


if __name__ == "__main__":
    unittest.main()
