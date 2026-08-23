import base64
import json
from pathlib import Path
import random
import tempfile
import unittest

from observer import DomainObserver
from trace_format import MappingSpec


def make_mapping(width=2, height=1, frequencies=(1, 3, 2)):
    patterns = [
        {"id": 10 + i, "frequency": frequency, "width": 1, "height": 1,
         "rgba": base64.b64encode(bytes((i * 50, 20, 200, 255))).decode("ascii")}
        for i, frequency in enumerate(frequencies)
    ]
    variables = []
    var = 1
    for y in range(height):
        for x in range(width):
            for pattern in patterns:
                variables.append({"var": var, "x": x, "y": y, "pattern_id": pattern["id"]})
                var += 1
    value = {"grid": {"width": width, "height": height}, "patterns": patterns, "variables": variables}
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "mapping.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return directory, MappingSpec.load(path)


class ObserverTests(unittest.TestCase):
    def test_nested_backtrack_restores_exact_domains(self):
        directory, mapping = make_mapping()
        self.addCleanup(directory.cleanup)
        events = []
        observer = DomainObserver(mapping, events.append)
        observer.on_assignment(-1, fixed=True)
        root = observer.domain_ids(0, 0)
        observer.on_new_level()
        observer.on_assignment(-2)
        level_one = observer.domain_ids(0, 0)
        observer.on_new_level()
        observer.on_assignment(3)
        observer.on_assignment(-4)
        observer.on_backtrack(1)
        self.assertEqual(observer.domain_ids(0, 0), level_one)
        self.assertEqual(observer.domain_ids(1, 0), (10, 11, 12))
        observer.on_backtrack(0)
        self.assertEqual(observer.domain_ids(0, 0), root)
        self.assertEqual(events[-2][0], "b")
        self.assertEqual(events[-1][0], "r")

    def test_root_assignments_survive_restart(self):
        directory, mapping = make_mapping(width=1)
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None)
        observer.on_assignment(-1, fixed=True)
        observer.on_new_level()
        observer.on_assignment(2)
        observer.on_backtrack(0)
        self.assertEqual(observer.domain_ids(0, 0), (11, 12))

    def test_solver_heuristic_defers(self):
        directory, mapping = make_mapping(width=1)
        self.addCleanup(directory.cleanup)
        self.assertEqual(DomainObserver(mapping, lambda event: None).decide(), 0)

    def test_wfc_selects_smallest_domain_deterministically(self):
        directory, mapping = make_mapping()
        self.addCleanup(directory.cleanup)
        first = DomainObserver(mapping, lambda event: None, heuristic="wfc", seed=7)
        second = DomainObserver(mapping, lambda event: None, heuristic="wfc", seed=7)
        first.on_assignment(-1)
        second.on_assignment(-1)
        decision = first.decide()
        self.assertEqual(decision, second.decide())
        self.assertIn(decision, (2, 3))

    def test_check_model_requires_one_positive_per_cell(self):
        directory, mapping = make_mapping()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None)
        self.assertTrue(observer.check_model([1, -2, -3, -4, 5, -6]))
        self.assertFalse(observer.check_model([1, 2, -3, -4, 5, -6]))


if __name__ == "__main__":
    unittest.main()
