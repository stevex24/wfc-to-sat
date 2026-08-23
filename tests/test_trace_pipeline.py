import argparse
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from solve_trace import read_dimacs
from trace_format import clauses_satisfied, read_trace


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "visualizer"


def replay(path):
    records = list(read_trace(path))
    header, events = records[0], records[1:]
    pattern_ids = [item["id"] for item in header["patterns"]]
    width, height = header["grid"]["width"], header["grid"]["height"]
    domains = [set(pattern_ids) for _ in range(width * height)]
    selected = [None] * len(domains)
    trails = [[]]
    level = 0
    for event in events:
        kind = event[0]
        if kind == "l":
            level = event[1]
            while len(trails) <= level:
                trails.append([])
        elif kind in {"p", "n"}:
            cell = event[2] * width + event[1]
            while len(trails) <= event[4]:
                trails.append([])
            trails[event[4]].append((cell, set(domains[cell]), selected[cell]))
            if kind == "p":
                domains[cell] = {event[3]}
                selected[cell] = event[3]
            else:
                domains[cell].discard(event[3])
                assert len(domains[cell]) == event[5]
        elif kind == "b":
            for old_level in range(level, event[1], -1):
                for cell, old_domain, old_selected in reversed(trails[old_level]):
                    domains[cell], selected[cell] = old_domain, old_selected
                trails[old_level].clear()
            level = event[1]
    return header, events, domains


class TracePipelineTests(unittest.TestCase):
    def test_checked_sat_traces_finish_collapsed_and_satisfy_cnf(self):
        num_vars, clauses = read_dimacs(EXAMPLE / "pipes-8x8.cnf")
        for name in ("pipes-solver.jsonl.gz", "pipes-wfc.jsonl.gz"):
            with self.subTest(name=name):
                header, events, domains = replay(EXAMPLE / name)
                self.assertEqual(events[-1][0:2], ["e", "sat"])
                self.assertTrue(all(len(domain) == 1 for domain in domains))
                by_cell_pattern = {(x, y, pattern_id): var for var, x, y, pattern_id in header["variables"]}
                model = []
                for y in range(header["grid"]["height"]):
                    for x in range(header["grid"]["width"]):
                        selected = next(iter(domains[y * header["grid"]["width"] + x]))
                        for pattern_id in [item["id"] for item in header["patterns"]]:
                            var = by_cell_pattern[(x, y, pattern_id)]
                            model.append(var if pattern_id == selected else -var)
                self.assertTrue(clauses_satisfied(clauses, model))
                compatibility = header["compatibility"]
                width, height = header["grid"]["width"], header["grid"]["height"]
                for y in range(height):
                    for x in range(width):
                        pattern = next(iter(domains[y * width + x]))
                        if x + 1 < width:
                            neighbor = next(iter(domains[y * width + x + 1]))
                            self.assertIn(neighbor, compatibility["right"][str(pattern)])
                        if y + 1 < height:
                            neighbor = next(iter(domains[(y + 1) * width + x]))
                            self.assertIn(neighbor, compatibility["down"][str(pattern)])

    def test_unsat_trace_has_no_model_event(self):
        _, events, _ = replay(EXAMPLE / "pipes-unsat.jsonl.gz")
        self.assertEqual(events[-1][0:2], ["e", "unsat"])
        self.assertNotIn("m", [event[0] for event in events])

    def test_trace_terminal_record_is_last(self):
        for path in EXAMPLE.glob("*.jsonl.gz"):
            events = list(read_trace(path))[1:]
            self.assertEqual(events[-1][0], "e", path.name)

    def test_instrumented_solver_writes_sat_and_unsat_terminals(self):
        try:
            import pysat  # noqa: F401
        except ImportError:
            self.skipTest("PySAT is not visible in the test sandbox")
        from solve_trace import solve
        with tempfile.TemporaryDirectory() as directory:
            for cnf_name, expected, terminal in (
                ("pipes-8x8.cnf", True, "sat"),
                ("pipes-8x8-unsat.cnf", False, "unsat"),
            ):
                with self.subTest(cnf=cnf_name):
                    output = Path(directory) / f"{cnf_name}.jsonl.gz"
                    args = argparse.Namespace(
                        cnf=EXAMPLE / cnf_name,
                        mapping=EXAMPLE / "pipes-8x8.map.json",
                        output=output,
                        heuristic="wfc" if expected else "solver",
                        seed=9,
                        solver="cadical195",
                        watchable=True,
                        cadical_option=[],
                    )
                    self.assertEqual(solve(args), expected)
                    records = list(read_trace(output))
                    self.assertEqual(records[-1][0:2], ["e", terminal])


if __name__ == "__main__":
    unittest.main()
