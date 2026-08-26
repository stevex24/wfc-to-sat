import tempfile
import unittest
from pathlib import Path

from PIL import Image

from experiments.context_sensitive.generate_letter_z import letter_z_pixels, write_letter_z
from experiments.context_sensitive.lag_r_metrics import displacement_pair_counts
from observer import DomainObserver
from tests.test_sat_context_heuristics import mapping_with_context
from wfc_to_sat.context_frequency import MOORE, UNK, ContextFrequencies, masked_contexts
from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel


class MooreContextTests(unittest.TestCase):
    def test_order_is_n_ne_e_se_s_sw_w_nw(self):
        self.assertEqual(MOORE, ((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1)))

    def test_diagonal_source_context_and_boundary_unknowns(self):
        source = (("a","b","c"),("d","e","f"),("g","h","i"))
        table = ContextFrequencies(source, "moore")
        self.assertEqual(table.complete_contexts[4][1], ("b","c","f","i","h","g","d","a"))
        self.assertEqual(table.complete_contexts[0][1], (UNK,UNK,"b","e","d",UNK,UNK,UNK))

    def test_eight_known_neighbors_produce_256_masks(self):
        variants = masked_contexts(tuple("abcdefgh"))
        self.assertEqual(len(variants), 256)
        self.assertEqual(len(set(variants)), 256)

    def test_tiny_exact_counts_and_fallback(self):
        source = (("A","B","A"),("B","A","B"),("A","B","A"))
        table = ContextFrequencies(source, "moore")
        center = ("B","A","B","A","B","A","B","A")
        self.assertEqual(table.frequency("A", center), 1)
        lookup = table.candidate_weights(("A","B"), ("A",)*8)
        self.assertEqual(lookup.weights, (5,4))
        self.assertTrue(lookup.used_frequency_fallback)

    def test_ordinary_wfc_moore_is_deterministic_and_uses_diagonals(self):
        model = WFCModel.from_tile_grid((("A","B","A"),("B","A","B"),("A","B","A")))
        left = OrdinaryWFC(model, 3, 3, decision="context_moore", seed=7)
        right = OrdinaryWFC(model, 3, 3, decision="context_moore", seed=7)
        self.assertEqual(left.run(), right.run())
        probe = OrdinaryWFC(model, 3, 3, decision="context_moore", seed=0)
        probe.collapse_to(0, 0, "A")
        self.assertEqual(len(probe.context_at(1, 1)), 8)
        self.assertEqual(probe.context_at(1, 1)[7], "A")

    def test_letter_z_exact_construction_and_png(self):
        pixels = letter_z_pixels()
        self.assertEqual((len(pixels[0]), len(pixels)), (16,16))
        for y, row in enumerate(pixels):
            for x, pixel in enumerate(row):
                expected_black = y in (0,15) or x+y == 15
                self.assertEqual(pixel[:3] == (0,0,0), expected_black)
        with tempfile.TemporaryDirectory() as directory:
            path = write_letter_z(Path(directory)/"letter-z.png")
            with Image.open(path) as image:
                self.assertEqual(image.size, (16,16))
                self.assertEqual(image.mode, "RGBA")

    def test_diagonal_pair_counts_keep_directions_separate(self):
        grid = (("a","b","c"),("d","e","f"),("g","h","i"))
        self.assertEqual(displacement_pair_counts(grid, 1, 1), {("a","e"):1,("b","f"):1,("d","h"):1,("e","i"):1})
        self.assertEqual(displacement_pair_counts(grid, -1, 1), {("b","d"):1,("c","e"):1,("e","g"):1,("f","h"):1})

    def test_sat_moore_diagonal_context_restores_across_nested_backtracking(self):
        directory, _, mapping = mapping_with_context(width=3, height=2)
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context_moore")
        # Cell (0,0), pattern 10 is NW of target (1,1).
        observer.on_new_level()
        observer.on_assignment(1)
        self.assertEqual(observer.context_at(1,1)[7], 10)
        observer.on_new_level()
        observer.on_assignment(4)
        observer.on_backtrack(1)
        self.assertEqual(observer.context_at(1,1)[7], 10)
        observer.on_backtrack(0)
        self.assertIs(observer.context_at(1,1)[7], UNK)

    def test_sat_moore_restart_and_repeated_solving_drop_abandoned_diagonal(self):
        directory, _, mapping = mapping_with_context(width=3, height=2)
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context_moore")
        observer.on_assignment(-1, fixed=True)
        observer.on_assignment(-2, fixed=True)
        observer.on_new_level()
        observer.on_assignment(4)
        observer.on_backtrack(0)
        self.assertEqual(observer.context_at(1,1)[7], 12)
        self.assertIs(observer.context_at(0,1)[1], UNK)
        observer.on_new_level()
        observer.on_assignment(5)
        self.assertEqual(observer.context_at(0,1)[1], 11)


if __name__ == "__main__":
    unittest.main()
