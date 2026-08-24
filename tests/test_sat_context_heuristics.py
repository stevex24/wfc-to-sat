import base64
import json
from pathlib import Path
import tempfile
import unittest

from observer import DomainObserver
from trace_format import MappingSpec
from wfc_to_sat.context_frequency import ContextFrequencies, UNK


def mapping_with_context(width=3, height=2):
    pattern_ids = (10, 11, 12)
    patterns = [
        {
            "id": pattern_id, "frequency": frequency, "width": 1, "height": 1,
            "rgba": base64.b64encode(bytes((index * 50, 20, 200, 255))).decode("ascii"),
        }
        for index, (pattern_id, frequency) in enumerate(zip(pattern_ids, (3, 2, 1)))
    ]
    variables = []
    variable = 1
    for y in range(height):
        for x in range(width):
            for pattern_id in pattern_ids:
                variables.append({"var": variable, "x": x, "y": y, "pattern_id": pattern_id})
                variable += 1
    value = {
        "mapping_version": 2,
        "grid": {"width": width, "height": height},
        "patterns": patterns,
        "variables": variables,
        "context_data": {
            "kind": "source-pattern-occurrences", "boundary": "unknown",
            "grid": [[10, 11, 10], [12, 10, 11]],
        },
    }
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "mapping.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return directory, path, MappingSpec.load(path)


class SatContextHeuristicTests(unittest.TestCase):
    def test_mapping_context_round_trip(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "roundtrip.json"
        path.write_text(json.dumps(mapping.to_json()), encoding="utf-8")
        self.assertEqual(MappingSpec.load(path), mapping)

    def test_uniform_and_frequency_weights(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        uniform = DomainObserver(mapping, lambda event: None, heuristic="uniform")
        frequency = DomainObserver(mapping, lambda event: None, heuristic="frequency")
        self.assertEqual(uniform.decision_weights(0), (1, 1, 1))
        self.assertEqual(frequency.decision_weights(0), (3, 2, 1))

    def test_context_weights_equal_shared_lookup(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context")
        # Propagation-style negative assignments make the western neighbor singleton.
        observer.on_assignment(-1)
        observer.on_assignment(-2)
        self.assertEqual(observer.context_at(1, 0), (UNK, UNK, UNK, 12))
        shared = ContextFrequencies(mapping.source_pattern_grid)
        expected = shared.candidate_weights((10, 11, 12), observer.context_at(1, 0)).weights
        self.assertEqual(observer.decision_weights(1), expected)

    def test_unseen_context_falls_back_to_frequency(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context")
        # Center's N/E/S/W context of all 12s is absent from the source.
        for variable in (4, 5, 10, 11, 16, 17):
            observer.on_assignment(-variable)
        self.assertEqual(observer.context_at(1, 1), (12, 12, UNK, 12))
        self.assertEqual(observer.decision_weights(4), (3, 2, 1))

    def test_nested_backtrack_removes_abandoned_context(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context")
        observer.on_new_level()
        observer.on_assignment(1)
        self.assertEqual(observer.context_at(1, 0)[3], 10)
        observer.on_new_level()
        observer.on_assignment(4)
        observer.on_backtrack(1)
        self.assertEqual(observer.domain_ids(1, 0), (10, 11, 12))
        observer.on_backtrack(0)
        self.assertIs(observer.context_at(1, 0)[3], UNK)

    def test_restart_preserves_root_and_discards_branch_singletons(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context")
        observer.on_assignment(-1, fixed=True)
        observer.on_assignment(-2, fixed=True)
        observer.on_new_level()
        observer.on_assignment(4)
        observer.on_backtrack(0)
        self.assertEqual(observer.context_at(1, 0)[3], 12)
        self.assertEqual(observer.domain_ids(1, 0), (10, 11, 12))

    def test_repeated_search_starts_from_restored_state(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        observer = DomainObserver(mapping, lambda event: None, heuristic="context")
        observer.on_new_level()
        observer.on_assignment(1)
        observer.on_backtrack(0)
        self.assertIs(observer.context_at(1, 0)[3], UNK)
        observer.on_new_level()
        observer.on_assignment(2)
        self.assertEqual(observer.context_at(1, 0)[3], 11)

    def test_seeded_decisions_are_reproducible_and_lexical(self):
        directory, _, mapping = mapping_with_context()
        self.addCleanup(directory.cleanup)
        left = DomainObserver(mapping, lambda event: None, heuristic="uniform", seed=9, selection="lexical")
        right = DomainObserver(mapping, lambda event: None, heuristic="uniform", seed=9, selection="lexical")
        self.assertEqual(left.decide(), right.decide())
        self.assertIn(left.decide(), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
