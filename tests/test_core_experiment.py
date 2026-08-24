import unittest

from experiments.context_sensitive.core_experiment import (
    distribution, kl_target_source, make_sat_instance, run_sat, source_grid,
)
from wfc_to_sat.ordinary_wfc import WFCModel


class CoreExperimentTests(unittest.TestCase):
    def test_paper_kl_direction_and_oriented_edge_domain(self):
        source = ("BW", "BB")
        target = ("BB", "BB")
        tile = kl_target_source(distribution(target), distribution(source))
        self.assertAlmostEqual(tile, -__import__("math").log(0.75))
        edges = distribution(source, edge=True)
        self.assertIn(("H", "B", "W"), edges)
        self.assertIn(("V", "W", "B"), edges)

    def test_completed_context_sat_model_is_legal(self):
        model = WFCModel.from_tile_grid(source_grid())
        cnf, mapping, tile_for_id = make_sat_instance(model, 4, 4)
        result = run_sat(cnf, mapping, tile_for_id, "context", 3)
        self.assertTrue(result["success"])
        rows = result["output"]
        self.assertEqual((len(rows), len(rows[0])), (4, 4))
        self.assertFalse(any("WW" in row for row in rows))


if __name__ == "__main__":
    unittest.main()
