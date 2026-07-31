"""Run the exhaustive CNF semantic validator and print a concise report.

Run from the repository root with either:

    python3 -m tests.validate_cnf
    python3 tests/validate_cnf.py
"""

from copy import deepcopy
from pathlib import Path
import sys


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.compatibility import build_compatibility
from wfc_to_sat.patterns import Pattern

from tests._semantic_oracle import compare_cnf_to_tilings


CASES = (
    (
        "alternating 2x2",
        [
            Pattern(id=3, rows=("AB", "BA")),
            Pattern(id=11, rows=("BA", "AB")),
        ],
        2,
        2,
    ),
    (
        "alternating 3x3",
        [
            Pattern(id=3, rows=("AB", "BA")),
            Pattern(id=11, rows=("BA", "AB")),
        ],
        3,
        3,
    ),
    (
        "direction-sensitive 2x2",
        [
            Pattern(id=2, rows=("AA", "AB")),
            Pattern(id=5, rows=("AB", "BB")),
            Pattern(id=9, rows=("BB", "BA")),
        ],
        2,
        2,
    ),
    (
        "unsatisfiable 2x2",
        [Pattern(id=7, rows=("AB", "CD"))],
        2,
        2,
    ),
)


def validate_case(patterns, width, height):
    """Compile one case and compare its CNF with the independent semantics."""
    allowed = build_compatibility(patterns)
    cnf = patterns_to_cnf(patterns, allowed, width, height)
    return compare_cnf_to_tilings(cnf, patterns, width, height)


def mutation_demonstrations():
    """Return detection results for two deliberately corrupted CNF copies."""
    _, patterns, width, height = CASES[0]
    allowed = build_compatibility(patterns)
    original = patterns_to_cnf(patterns, allowed, width, height)
    demonstrations = []

    missing_clause = deepcopy(original)
    del missing_clause.clauses[0]
    try:
        compare_cnf_to_tilings(missing_clause, patterns, width, height)
    except (AssertionError, ValueError) as error:
        demonstrations.append(("remove required clause", True, str(error)))
    else:
        demonstrations.append(("remove required clause", False, "not detected"))

    changed_literal = deepcopy(original)
    overlap_clause = next(
        clause
        for clause in changed_literal.clauses
        if len(clause) == 2
        and all(literal < 0 for literal in clause)
        and changed_literal.name_map[-clause[0]][:2]
        != changed_literal.name_map[-clause[1]][:2]
    )
    overlap_clause[0] = -overlap_clause[0]
    try:
        compare_cnf_to_tilings(changed_literal, patterns, width, height)
    except (AssertionError, ValueError) as error:
        demonstrations.append(("negate overlap literal", True, str(error)))
    else:
        demonstrations.append(("negate overlap literal", False, "not detected"))

    return demonstrations


def main():
    """Validate all bounded cases and print their model counts."""
    print("Exhaustive CNF validation")

    all_identical = True
    for name, patterns, width, height in CASES:
        report = validate_case(patterns, width, height)
        identical = "yes" if report.sets_identical else "NO"
        print(
            f"{name}: legal tilings={report.legal_tilings}, "
            f"SAT solutions={report.sat_solutions}, "
            f"sets identical={identical}"
        )
        all_identical &= report.sets_identical

    print("Mutation checks")
    for name, detected, detail in mutation_demonstrations():
        print(
            f"{name}: {'DETECTED' if detected else 'MISSED'}"
            f" ({detail})"
        )
        all_identical &= detected

    print(f"Overall: {'PASS' if all_identical else 'FAIL'}")
    return 0 if all_identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
