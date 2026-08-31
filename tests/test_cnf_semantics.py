import unittest
from itertools import product

from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import Pattern

from tests._semantic_oracle import (
    assert_cnf_matches_tilings,
    assert_cnf_structure,
)
from tests.validate_cnf import mutation_demonstrations


class CnfSemanticTests(unittest.TestCase):
    @staticmethod
    def one_cell_formula(candidate_count, encoding):
        patterns = [Pattern(i, ((str(i),),), 1) for i in range(candidate_count)]
        allowed = {
            "right": {i: list(range(candidate_count)) for i in range(candidate_count)},
            "down": {i: list(range(candidate_count)) for i in range(candidate_count)},
        }
        return patterns_to_cnf(
            patterns, allowed, 1, 1, exactly_one_encoding=encoding
        )

    def test_pairwise_and_sequential_accept_same_placement_assignments(self):
        from pysat.solvers import Cadical195

        for candidate_count in range(1, 6):
            pairwise = self.one_cell_formula(candidate_count, "pairwise")
            sequential = self.one_cell_formula(candidate_count, "sequential")
            placements = sorted(pairwise.name_map)
            self.assertEqual(placements, sorted(sequential.name_map))
            for values in product((False, True), repeat=candidate_count):
                assumptions = [variable if value else -variable for variable, value in zip(placements, values)]
                with Cadical195(bootstrap_with=pairwise.clauses) as left:
                    pairwise_sat = left.solve(assumptions=assumptions)
                with Cadical195(bootstrap_with=sequential.clauses) as right:
                    sequential_sat = right.solve(assumptions=assumptions)
                self.assertEqual(pairwise_sat, sequential_sat)
                self.assertEqual(pairwise_sat, sum(values) == 1)

    def test_sequential_exactly_one_rejects_zero_and_multiple_candidates(self):
        from pysat.solvers import Cadical195

        cnf = self.one_cell_formula(4, "sequential")
        placements = sorted(cnf.name_map)
        with Cadical195(bootstrap_with=cnf.clauses) as solver:
            self.assertFalse(solver.solve(assumptions=[-var for var in placements]))
            for selected in placements:
                assumptions = [var if var == selected else -var for var in placements]
                self.assertTrue(solver.solve(assumptions=assumptions))
            self.assertFalse(solver.solve(assumptions=[placements[0], placements[1]]))
            self.assertFalse(solver.solve(assumptions=placements))

    def test_sequential_auxiliary_variables_are_disjoint_and_unnamed(self):
        cnf = self.one_cell_formula(4, "sequential")
        placements = set(cnf.name_map)
        auxiliaries = set(range(1, cnf.num_vars + 1)) - placements
        self.assertEqual(placements, {1, 2, 3, 4})
        self.assertEqual(auxiliaries, {5, 6, 7})
        self.assertTrue(placements.isdisjoint(auxiliaries))
        self.assertEqual(set(cnf.var_map.values()), placements)

    def test_domain_observer_maps_only_sequential_placement_variables(self):
        from observer import DomainObserver
        from trace_format import MappingSpec, PatternSpec, Placement

        cnf = self.one_cell_formula(4, "sequential")
        specs = tuple(PatternSpec(i, 1, 1, 1, bytes((i, 0, 0, 255))) for i in range(4))
        placements = tuple(
            Placement(variable, x, y, pattern_id)
            for variable, (x, y, pattern_id) in sorted(cnf.name_map.items())
        )
        mapping = MappingSpec(1, 1, specs, placements)
        mapping.validate(num_vars=cnf.num_vars)
        observer = DomainObserver(mapping, lambda event: None, heuristic="solver")
        auxiliaries = set(range(1, cnf.num_vars + 1)) - set(cnf.name_map)
        self.assertEqual(set(observer.var_info), set(cnf.name_map))
        self.assertTrue(auxiliaries.isdisjoint(observer.var_info))

    def test_small_end_to_end_pairwise_and_sequential_regressions(self):
        from pysat.solvers import Cadical195
        from trace_format import clauses_satisfied

        cases = (
            ("alternating-sat", [Pattern(3, ("AB", "BA")), Pattern(11, ("BA", "AB"))], 2, 2),
            ("alternating-sat-wide", [Pattern(3, ("AB", "BA")), Pattern(11, ("BA", "AB"))], 3, 2),
            ("single-pattern-unsat", [Pattern(7, ("AB", "CD"))], 2, 2),
        )
        for name, patterns, width, height in cases:
            allowed = build_compatibility(patterns)
            results = {}
            for encoding in ("pairwise", "sequential"):
                cnf = patterns_to_cnf(
                    patterns, allowed, width, height,
                    exactly_one_encoding=encoding,
                )
                with Cadical195(bootstrap_with=cnf.clauses) as solver:
                    sat = solver.solve()
                    model = solver.get_model() if sat else []
                results[encoding] = sat
                if sat:
                    self.assertTrue(clauses_satisfied(cnf.clauses, model), name)
                    positive = {literal for literal in model if literal > 0}
                    selected = {
                        (x, y): pattern_id
                        for variable, (x, y, pattern_id) in cnf.name_map.items()
                        if variable in positive
                    }
                    self.assertEqual(len(selected), width * height, name)
                    for y in range(height):
                        for x in range(width):
                            pattern_id = selected[(x, y)]
                            if x + 1 < width:
                                self.assertIn(selected[(x + 1, y)], allowed["right"][pattern_id], name)
                            if y + 1 < height:
                                self.assertIn(selected[(x, y + 1)], allowed["down"][pattern_id], name)
            self.assertEqual(results["pairwise"], results["sequential"], name)

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
