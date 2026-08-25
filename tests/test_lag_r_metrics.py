import math
import unittest
from collections import Counter

from experiments.context_sensitive.core_experiment import distribution, kl_target_source
from experiments.context_sensitive.lag_r_metrics import (
    aggregate_lag_counts, lag_kl, lag_pair_counts, normalized,
)


class LagRMetricTests(unittest.TestCase):
    GRID = (("A", "B", "A"), ("C", "A", "B"))

    def test_exact_horizontal_ordered_counts_and_boundaries(self):
        self.assertEqual(lag_pair_counts(self.GRID, 1, "horizontal"),
                         Counter({("A", "B"): 2, ("B", "A"): 1, ("C", "A"): 1}))
        self.assertEqual(lag_pair_counts(self.GRID, 2, "horizontal"),
                         Counter({("A", "A"): 1, ("C", "B"): 1}))
        self.assertNotEqual(lag_pair_counts(self.GRID, 1, "horizontal")[("A", "B")],
                            lag_pair_counts(self.GRID, 1, "horizontal")[("B", "A")])

    def test_exact_vertical_counts(self):
        self.assertEqual(lag_pair_counts(self.GRID, 1, "vertical"),
                         Counter({("A", "C"): 1, ("B", "A"): 1, ("A", "B"): 1}))

    def test_invalid_and_excessive_lags(self):
        for lag in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                lag_pair_counts(self.GRID, lag, "horizontal")
        with self.assertRaises(ValueError):
            lag_pair_counts(self.GRID, 3, "horizontal")
        with self.assertRaises(ValueError):
            lag_pair_counts(self.GRID, 2, "vertical")

    def test_lag_one_combines_to_existing_oriented_edge_distribution(self):
        old = distribution(self.GRID, edge=True)
        combined = Counter()
        combined.update({("H", *pair): count for pair, count in lag_pair_counts(self.GRID, 1, "horizontal").items()})
        combined.update({("V", *pair): count for pair, count in lag_pair_counts(self.GRID, 1, "vertical").items()})
        self.assertEqual(normalized(combined), old)

    def test_deterministic_aggregation_and_zero_for_identical_grids(self):
        expected = lag_pair_counts(self.GRID, 1, "horizontal")
        self.assertEqual(aggregate_lag_counts([self.GRID], 1, "horizontal"), expected)
        self.assertEqual(aggregate_lag_counts([self.GRID, self.GRID], 1, "horizontal"),
                         Counter({key: 2 * value for key, value in expected.items()}))
        self.assertAlmostEqual(lag_kl([self.GRID], self.GRID, 1, "horizontal"), 0.0)

    def test_kl_reuses_established_convention(self):
        target = normalized(Counter({("A", "B"): 3, ("B", "A"): 1}))
        source = normalized(Counter({("A", "B"): 2, ("B", "A"): 2}))
        self.assertEqual(kl_target_source(target, source),
                         sum(p * math.log(p / source[k]) for k, p in target.items()))
        self.assertEqual(kl_target_source({("new", "pair"): 1.0}, source), math.inf)

    def test_identical_stick_wfc_sat_outputs_have_identical_measurements(self):
        import json
        from pathlib import Path
        data = json.loads(Path("context-sensitive-results/core-comparison/raw-runs.json").read_text())
        runs = data["runs"]
        for decision in ("uniform", "frequency", "context"):
            wfc = next(r for r in runs if r["seed"] == 0 and r["decision"] == decision and r["engine"] == "ordinary WFC")
            sat = next(r for r in runs if r["seed"] == 0 and r["decision"] == decision and r["engine"] == "WFC-as-SAT")
            self.assertEqual(wfc["output"], sat["output"])
            for axis in ("horizontal", "vertical"):
                self.assertEqual(lag_pair_counts(wfc["output"], 2, axis),
                                 lag_pair_counts(sat["output"], 2, axis))


if __name__ == "__main__":
    unittest.main()
