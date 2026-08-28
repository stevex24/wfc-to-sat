import unittest

from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import Pattern

from tests._semantic_oracle import (
    assert_cnf_matches_tilings,
    assert_cnf_structure,
)
from tests.validate_cnf import mutation_demonstrations


class CnfSemanticTests(unittest.TestCase):
    def test_support_and_forbidden_pair_adjacency_encodings_are_equivalent(self):
        from itertools import product
        from wfc_to_sat.cnf import patterns_to_cnf
        from wfc_to_sat.patterns import Pattern

        patterns = [Pattern(0, (("A",),), 1), Pattern(1, (("B",),), 1)]
        allowed = {
            "right": {0: [1], 1: [0, 1]},
            "down": {0: [0, 1], 1: [0]},
        }
        left = patterns_to_cnf(patterns, allowed, 2, 2)
        right = patterns_to_cnf(
            patterns, allowed, 2, 2, adjacency_encoding="support"
        )

        def satisfies(builder, assignment):
            return all(any(assignment[abs(lit)] == (lit > 0) for lit in clause) for clause in builder.clauses)

        self.assertEqual(left.num_vars, right.num_vars)
        for values in product((False, True), repeat=left.num_vars):
            assignment = {index + 1: value for index, value in enumerate(values)}
            self.assertEqual(satisfies(left, assignment), satisfies(right, assignment))

    def assert_compiler_matches_semantics(self, patterns, width, height):
        allowed = build_compatibility(patterns)
        cnf = patterns_to_cnf(patterns, allowed, width, height)

        assert_cnf_structure(self, cnf, patterns, width, height)
        assert_cnf_matches_tilings(
            self,
            cnf,
            patterns,
            width,
            height,
        )

    def test_alternating_patterns_on_two_by_two_grid(self):
        patterns = [
            Pattern(id=3, rows=("AB", "BA")),
            Pattern(id=11, rows=("BA", "AB")),
        ]

        self.assert_compiler_matches_semantics(patterns, width=2, height=2)

    def test_alternating_patterns_on_three_by_three_grid(self):
        patterns = [
            Pattern(id=3, rows=("AB", "BA")),
            Pattern(id=11, rows=("BA", "AB")),
        ]

        self.assert_compiler_matches_semantics(patterns, width=3, height=3)

    def test_horizontal_and_vertical_compatibility_differ(self):
        patterns = [
            Pattern(id=2, rows=("AA", "AB")),
            Pattern(id=5, rows=("AB", "BB")),
            Pattern(id=9, rows=("BB", "BA")),
        ]

        self.assert_compiler_matches_semantics(patterns, width=2, height=2)

    def test_instance_with_no_legal_tiling_is_unsatisfiable(self):
        patterns = [
            Pattern(id=7, rows=("AB", "CD")),
        ]

        self.assert_compiler_matches_semantics(patterns, width=2, height=2)

    def test_deliberately_corrupted_encodings_are_detected(self):
        for name, detected, detail in mutation_demonstrations():
            with self.subTest(mutation=name):
                self.assertTrue(detected, detail)


if __name__ == "__main__":
    unittest.main()
