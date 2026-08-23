import inspect
import unittest

import wfc_to_sat.ordinary_wfc as ordinary_wfc_module
from wfc_to_sat.context_frequency import UNK
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.ordinary_wfc import OrdinaryWFC, WFCModel
from wfc_to_sat.patterns import Pattern


CHECKER = (("A", "B"), ("B", "A"))


def unconstrained_model(source):
    contexts = WFCModel.from_tile_grid(source).context_frequencies
    tiles = tuple(dict.fromkeys(tile for row in source for tile in row))
    all_tiles = {tile: tiles for tile in tiles}
    return WFCModel(
        tiles=tiles,
        frequencies={tile: sum(row.count(tile) for row in source) for tile in tiles},
        adjacency={
            "north": all_tiles,
            "east": all_tiles,
            "south": all_tiles,
            "west": all_tiles,
        },
        context_frequencies=contexts,
    )


class OrdinaryWFCTests(unittest.TestCase):
    def test_domains_initialize_to_every_tile_in_source_order(self):
        engine = OrdinaryWFC(WFCModel.from_tile_grid(CHECKER), 2, 2, seed=4)
        for y in range(2):
            for x in range(2):
                self.assertEqual(engine.domain_at(x, y), ("A", "B"))

    def test_lexical_selection_is_left_to_right_then_top_to_bottom(self):
        engine = OrdinaryWFC(WFCModel.from_tile_grid(CHECKER), 3, 2)
        self.assertEqual(engine.select_location(), (0, 0))
        self.assertTrue(engine.collapse_to(0, 0, "A"))
        self.assertIsNone(engine.select_location())

        unconstrained = unconstrained_model(CHECKER)
        engine = OrdinaryWFC(unconstrained, 2, 2)
        self.assertTrue(engine.collapse_to(0, 0, "A"))
        self.assertEqual(engine.select_location(), (1, 0))
        self.assertTrue(engine.collapse_to(1, 0, "B"))
        self.assertEqual(engine.select_location(), (0, 1))

    def test_propagation_reaches_a_hand_derived_fixed_point(self):
        engine = OrdinaryWFC(WFCModel.from_tile_grid(CHECKER), 3, 3)
        self.assertTrue(engine.collapse_to(0, 0, "A"))
        expected = (
            ("A", "B", "A"),
            ("B", "A", "B"),
            ("A", "B", "A"),
        )
        self.assertEqual(
            tuple(tuple(engine.domain_at(x, y)[0] for x in range(3)) for y in range(3)),
            expected,
        )
        self.assertTrue(engine.is_complete())
        self.assertEqual(engine.observed, {(0, 0)})

    def test_contradiction_is_an_empty_domain_and_stops_generation(self):
        engine = OrdinaryWFC(WFCModel.from_tile_grid((tuple("AB"),)), 3, 1)
        self.assertFalse(engine.collapse_to(0, 0, "A"))
        self.assertEqual(engine.domain_at(2, 0), ())
        self.assertTrue(engine.has_contradiction())
        result = engine.run()
        self.assertFalse(result.success)
        self.assertEqual(result.contradictions, 1)
        self.assertEqual(result.contradiction_policy, "stop")
        self.assertEqual((result.attempts, result.restarts), (1, 0))

    def test_uniform_and_frequency_weights_only_cover_legal_candidates(self):
        source = (tuple("AAB"),)
        model = WFCModel.from_tile_grid(source)
        uniform = OrdinaryWFC(model, 1, 1, decision="uniform")
        frequency = OrdinaryWFC(model, 1, 1, decision="frequency")
        self.assertEqual(uniform.decision_weights_at(0, 0).weights, (1, 1))
        self.assertEqual(frequency.decision_weights_at(0, 0).weights, (2, 1))

    def test_repository_pattern_compatibility_adapts_to_four_directions(self):
        patterns = (
            Pattern(id=3, rows=("AB", "BA"), frequency=4),
            Pattern(id=8, rows=("BA", "AB"), frequency=2),
        )
        allowed = build_compatibility(patterns)
        model = WFCModel.from_patterns(patterns, allowed)
        engine = OrdinaryWFC(model, 3, 3, decision="frequency")
        result = engine.run()

        self.assertEqual(model.adjacency["west"][3], (8,))
        self.assertEqual(model.adjacency["north"][3], (8,))
        self.assertTrue(result.success)
        self._assert_output_is_legal(result.output, model)

    def test_context_uses_propagation_singletons_and_shared_weights(self):
        model = WFCModel.from_tile_grid(CHECKER)
        engine = OrdinaryWFC(model, 3, 3, decision="context")
        self.assertTrue(engine.collapse_to(0, 0, "A"))
        self.assertNotIn((1, 0), engine.observed)
        self.assertEqual(engine.context_at(2, 0), (UNK, UNK, "B", "B"))

        context_source = (
            ("A", "B", "A"),
            ("B", "A", "B"),
            ("A", "B", "A"),
        )
        context_engine = OrdinaryWFC(
            unconstrained_model(context_source), 3, 3, decision="context"
        )
        for x, y in ((1, 0), (2, 1), (1, 2), (0, 1)):
            self.assertTrue(context_engine.collapse_to(x, y, "B"))
        weights = context_engine.decision_weights_at(1, 1)
        self.assertEqual(weights.candidates, ("A", "B"))
        self.assertEqual(weights.weights, (1, 0))
        self.assertFalse(weights.used_frequency_fallback)

    def test_context_falls_back_to_source_frequency_for_legal_subset(self):
        source = (("A", "B", "A"), ("B", "A", "B"), ("A", "B", "A"))
        engine = OrdinaryWFC(unconstrained_model(source), 3, 3, decision="context")
        for x, y in ((1, 0), (2, 1), (1, 2), (0, 1)):
            self.assertTrue(engine.collapse_to(x, y, "A"))
        weights = engine.decision_weights_at(1, 1)
        self.assertEqual(weights.weights, (5, 4))
        self.assertTrue(weights.used_frequency_fallback)

    def test_fixed_seed_is_repeatable_and_outputs_are_legal(self):
        model = WFCModel.from_tile_grid(
            (tuple("BBBBBBB"), tuple("BBBWBBB"), tuple("BBBWBBB"),
             tuple("BBBWBBB"), tuple("BBBWBBB"), tuple("BBBWBBB"),
             tuple("BBBBBBB"))
        )
        for decision in ("uniform", "frequency", "context"):
            first = OrdinaryWFC(model, 20, 20, decision=decision, seed=17).run()
            second = OrdinaryWFC(model, 20, 20, decision=decision, seed=17).run()
            self.assertEqual(first, second)
            self.assertTrue(first.success)
            self._assert_output_is_legal(first.output, model)

    def test_weighted_sampling_detects_gross_distribution_errors_without_flakiness(self):
        model = WFCModel.from_tile_grid((tuple("AAB"),))
        frequency_a = 0
        uniform_a = 0
        samples = 2000
        for seed in range(samples):
            frequency_a += OrdinaryWFC(
                model, 1, 1, decision="frequency", seed=seed
            ).run().output[0][0] == "A"
            uniform_a += OrdinaryWFC(
                model, 1, 1, decision="uniform", seed=seed
            ).run().output[0][0] == "A"
        self.assertGreater(frequency_a / samples, 0.62)
        self.assertLess(frequency_a / samples, 0.71)
        self.assertGreater(uniform_a / samples, 0.46)
        self.assertLess(uniform_a / samples, 0.54)

    def test_engine_has_no_sat_cdcl_dependency(self):
        source = inspect.getsource(ordinary_wfc_module)
        self.assertNotIn("pysat", source.lower())
        self.assertNotIn("cadical", source.lower())
        self.assertNotIn("domainobserver", source.lower())

    def _assert_output_is_legal(self, output, model):
        for y, row in enumerate(output):
            for x, tile in enumerate(row):
                self.assertIsNotNone(tile)
                if x + 1 < len(row):
                    self.assertIn(output[y][x + 1], model.adjacency["east"][tile])
                if y + 1 < len(output):
                    self.assertIn(output[y + 1][x], model.adjacency["south"][tile])


if __name__ == "__main__":
    unittest.main()
