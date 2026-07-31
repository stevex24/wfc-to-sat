"""Independent finite-model oracle for the WFC-to-SAT compiler.

This module intentionally does not import or call the compiler's overlap
predicates. Legality is derived directly from the rows of adjacent patterns.
"""

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class ValidationReport:
    """Summary of an exhaustive comparison between WFC and CNF models."""

    legal_tilings: int
    sat_solutions: int
    sets_identical: bool


def parse_dimacs(text):
    """Parse the compiler's DIMACS output without using compiler helpers."""
    num_vars = None
    declared_clauses = None
    clauses = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("c"):
            continue

        fields = line.split()
        if fields[0] == "p":
            if num_vars is not None or len(fields) != 4 or fields[1] != "cnf":
                raise ValueError(f"invalid DIMACS header on line {line_number}")
            num_vars = int(fields[2])
            declared_clauses = int(fields[3])
            continue

        if num_vars is None:
            raise ValueError("DIMACS clause appeared before the header")

        literals = [int(field) for field in fields]
        if not literals or literals[-1] != 0 or 0 in literals[:-1]:
            raise ValueError(f"invalid DIMACS clause on line {line_number}")
        clauses.append(literals[:-1])

    if num_vars is None:
        raise ValueError("DIMACS header is missing")
    if declared_clauses != len(clauses):
        raise ValueError(
            f"DIMACS declares {declared_clauses} clauses, found {len(clauses)}"
        )

    return num_vars, clauses


def tiling_is_legal(tiling, patterns_by_id):
    """Check every shared edge in a complete tiling directly from pattern rows."""
    height = len(tiling)
    width = len(tiling[0])

    for y in range(height):
        for x in range(width - 1):
            left = patterns_by_id[tiling[y][x]]
            right = patterns_by_id[tiling[y][x + 1]]

            for row in range(len(left.rows)):
                if left.rows[row][1:] != right.rows[row][:-1]:
                    return False

    for y in range(height - 1):
        for x in range(width):
            top = patterns_by_id[tiling[y][x]]
            bottom = patterns_by_id[tiling[y + 1][x]]

            if top.rows[1:] != bottom.rows[:-1]:
                return False

    return True


def enumerate_legal_tilings(patterns, width, height):
    """Enumerate all pattern placements and retain exactly the legal tilings."""
    patterns_by_id = {pattern.id: pattern for pattern in patterns}
    legal = set()

    for choices in product(patterns_by_id, repeat=width * height):
        tiling = tuple(
            tuple(choices[y * width : (y + 1) * width])
            for y in range(height)
        )

        if tiling_is_legal(tiling, patterns_by_id):
            legal.add(tiling)

    return legal


def assignment_satisfies(clauses, assignment):
    """Evaluate arbitrary CNF clauses against a total Boolean assignment."""
    for clause in clauses:
        if not any(
            assignment[abs(literal) - 1] == (literal > 0)
            for literal in clause
        ):
            return False

    return True


def assignment_for_tiling(cnf, tiling):
    """Create the compiler-defined Boolean assignment for a concrete tiling."""
    assignment = [False] * cnf.num_vars

    for y, row in enumerate(tiling):
        for x, pattern_id in enumerate(row):
            variable = cnf.var_map[(x, y, pattern_id)]
            assignment[variable - 1] = True

    return tuple(assignment)


def decode_assignment(cnf, assignment, pattern_ids, width, height):
    """Decode a total assignment, rejecting zero-hot and multi-hot cells."""
    selected = {(x, y): [] for y in range(height) for x in range(width)}

    for variable, value in enumerate(assignment, start=1):
        if value:
            x, y, pattern_id = cnf.name_map[variable]
            selected[(x, y)].append(pattern_id)

    for coordinate, choices in selected.items():
        if len(choices) != 1:
            raise ValueError(
                f"expected exactly one pattern at {coordinate}, got {choices}"
            )
        if choices[0] not in pattern_ids:
            raise ValueError(
                f"unknown pattern {choices[0]} selected at {coordinate}"
            )

    return tuple(
        tuple(selected[(x, y)][0] for x in range(width))
        for y in range(height)
    )


def enumerate_cnf_models(cnf, patterns, width, height):
    """Truth-table the CNF and group satisfying assignments by decoded tiling."""
    pattern_ids = {pattern.id for pattern in patterns}
    models = {}

    for assignment in product((False, True), repeat=cnf.num_vars):
        if not assignment_satisfies(cnf.clauses, assignment):
            continue

        tiling = decode_assignment(
            cnf,
            assignment,
            pattern_ids,
            width,
            height,
        )
        models.setdefault(tiling, []).append(assignment)

    return models


def assert_cnf_structure(testcase, cnf, patterns, width, height):
    """Check that the compiler exposed a complete and internally consistent map."""
    testcase.assertEqual(
        len({pattern.id for pattern in patterns}),
        len(patterns),
        "pattern IDs must be unique",
    )

    expected_names = {
        (x, y, pattern.id)
        for y in range(height)
        for x in range(width)
        for pattern in patterns
    }

    testcase.assertEqual(set(cnf.var_map), expected_names)
    testcase.assertEqual(
        set(cnf.name_map),
        set(range(1, cnf.num_vars + 1)),
    )
    testcase.assertEqual(len(cnf.var_map), cnf.num_vars)

    for name, variable in cnf.var_map.items():
        testcase.assertEqual(cnf.name_map[variable], name)

    seen_clauses = set()
    for clause in cnf.clauses:
        testcase.assertTrue(clause, "CNF must not contain an empty clause")
        testcase.assertEqual(
            len(clause),
            len(set(clause)),
            f"clause contains a repeated literal: {clause}",
        )
        testcase.assertFalse(
            any(-literal in clause for literal in clause),
            f"clause is tautological: {clause}",
        )
        normalized = tuple(sorted(clause))
        testcase.assertNotIn(
            normalized,
            seen_clauses,
            f"duplicate clause: {clause}",
        )
        seen_clauses.add(normalized)

        for literal in clause:
            testcase.assertGreaterEqual(abs(literal), 1)
            testcase.assertLessEqual(abs(literal), cnf.num_vars)

    dimacs_num_vars, dimacs_clauses = parse_dimacs(cnf.dimacs())
    testcase.assertEqual(dimacs_num_vars, cnf.num_vars)
    testcase.assertEqual(dimacs_clauses, cnf.clauses)


def compare_cnf_to_tilings(cnf, patterns, width, height):
    """Exhaustively compare semantic tilings with all satisfying assignments.

    Raises AssertionError if either implication fails. The returned report is
    suitable for human-readable output as well as test assertions.
    """
    patterns_by_id = {pattern.id: pattern for pattern in patterns}
    legal_tilings = enumerate_legal_tilings(patterns, width, height)

    for tiling in legal_tilings:
        assignment = assignment_for_tiling(cnf, tiling)
        if not assignment_satisfies(cnf.clauses, assignment):
            raise AssertionError(
                f"legal tiling does not satisfy CNF: {tiling}"
            )

    models = enumerate_cnf_models(cnf, patterns, width, height)

    for tiling, assignments in models.items():
        if not tiling_is_legal(tiling, patterns_by_id):
            raise AssertionError(
                f"CNF model decodes to illegal tiling: {tiling}; "
                f"assignment: {assignments[0]}"
            )

    sat_solutions = sum(len(assignments) for assignments in models.values())
    sets_identical = (
        set(models) == legal_tilings
        and sat_solutions == len(legal_tilings)
    )

    return ValidationReport(
        legal_tilings=len(legal_tilings),
        sat_solutions=sat_solutions,
        sets_identical=sets_identical,
    )


def assert_cnf_matches_tilings(testcase, cnf, patterns, width, height):
    """Assert exact equivalence and return the exhaustive validation report."""
    report = compare_cnf_to_tilings(cnf, patterns, width, height)
    testcase.assertTrue(report.sets_identical, report)
    return report
