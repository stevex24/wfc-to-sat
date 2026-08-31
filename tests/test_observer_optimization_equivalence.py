"""Decision-trace equivalence tests for DomainObserver hot-path optimizations."""

import hashlib
import random
import unittest

from observer import DomainObserver, _bit_count, _has_multiple_bits
from trace_format import MappingSpec, PatternSpec, Placement
from wfc_to_sat.cnf import patterns_to_cnf
from wfc_to_sat.patterns import Pattern
from wfc_to_sat.context_frequency import UNK


class LegacyDomainObserver(DomainObserver):
    """The pre-optimization selection/context implementation as an oracle."""

    def on_assignment(self, lit, fixed=False):
        info = self.var_info.get(abs(lit))
        if info is None:
            return
        cell, x, y, pattern_index = info
        old_domain, old_selected = self.domains[cell], self.selected[cell]
        if lit > 0:
            new_domain = self.pattern_bits[pattern_index]
            new_selected = pattern_index
        else:
            new_domain = old_domain & ~(1 << pattern_index)
            new_selected = old_selected
        self._ensure_level(self.current_level)
        self.trails[self.current_level].append((cell, old_domain, old_selected))
        self.domains[cell], self.selected[cell] = new_domain, new_selected
        pattern_id = self.pattern_ids[pattern_index]
        if lit > 0:
            self.emit(["p", x, y, pattern_id, self.current_level])
        else:
            self.emit(["n", x, y, pattern_id, self.current_level, _bit_count(new_domain)])

    def on_new_level(self):
        self.current_level += 1
        self._ensure_level(self.current_level)
        self.emit(["l", self.current_level])

    def on_backtrack(self, to):
        if to < 0:
            raise ValueError(f"invalid backtrack level {to}")
        if to > self.current_level:
            self._ensure_level(to)
            self.current_level = to
            self.emit(["b", to, 0])
            return
        undone = 0
        for level in range(self.current_level, to, -1):
            for cell, old_domain, old_selected in reversed(self.trails[level]):
                self.domains[cell], self.selected[cell] = old_domain, old_selected
                undone += 1
            self.trails[level].clear()
        self.current_level = to
        self.backtrack_events += 1
        self.undone_assignments += undone
        self.emit(["b", to, undone])
        if to == 0:
            self.restart_events += 1
            self.emit(["r", undone])

    def decide(self):
        if self.heuristic == "solver":
            return 0
        candidates = []
        for cell, domain in enumerate(self.domains):
            size = _bit_count(domain)
            if size <= 1 or self.selected[cell] is not None:
                continue
            if self.selection_heuristic == "lexical":
                candidates.append((0, 0.0, 0.0, cell))
            else:
                candidates.append((size, self._entropy(domain), self.random.random(), cell))
        if not candidates:
            return 0
        _, _, _, cell = min(candidates)
        indexes = [
            index for index in range(len(self.pattern_ids))
            if self.domains[cell] & (1 << index)
        ]
        weights = self.decision_weights(cell, indexes)
        chosen = self.random.choices(indexes, weights=weights, k=1)[0]
        return self.var_for_cell_pattern[(cell, chosen)]

    def context_at_cell(self, cell):
        x, y = cell % self.mapping.width, cell // self.mapping.width
        values = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.mapping.width and 0 <= ny < self.mapping.height):
                values.append(UNK)
                continue
            ids = self.domain_ids(nx, ny)
            values.append(ids[0] if len(ids) == 1 else UNK)
        return tuple(values)


class TraceMixin:
    def __init__(self, *args, **kwargs):
        self.decision_trace = []
        super().__init__(*args, **kwargs)

    def decide(self):
        cell = next(
            (cell for cell, domain in enumerate(self.domains)
             if _has_multiple_bits(domain) and self.selected[cell] is None),
            None,
        )
        snapshot = None
        if cell is not None:
            indexes = tuple(
                index for index in range(len(self.pattern_ids))
                if self.domains[cell] & (1 << index)
            )
            context = self.context_at_cell(cell)
            lookup = self.context_frequencies.candidate_weights(
                (self.pattern_ids[index] for index in indexes), context,
            )
            snapshot = (
                cell, indexes, context, lookup.weights,
                lookup.used_frequency_fallback,
            )
        result = super().decide()
        self.decision_trace.append((snapshot, result))
        return result


class TracedLegacy(TraceMixin, LegacyDomainObserver):
    pass


class TracedOptimized(TraceMixin, DomainObserver):
    pass


def make_problem(width=3, height=2):
    pattern_ids = (10, 11, 12)
    frequencies = (3, 2, 1)
    specs = tuple(
        PatternSpec(pattern_id, frequency, 1, 1, bytes((i, 0, 0, 255)))
        for i, (pattern_id, frequency) in enumerate(zip(pattern_ids, frequencies))
    )
    placements = []
    variable = 1
    for y in range(height):
        for x in range(width):
            for pattern_id in pattern_ids:
                placements.append(Placement(variable, x, y, pattern_id))
                variable += 1
    source = ((10, 11, 10), (12, 10, 11))
    return MappingSpec(width, height, specs, tuple(placements), source_pattern_grid=source)


def placement_hash(model, placement_variables):
    positive = sorted(set(model).intersection(placement_variables))
    return hashlib.sha256(",".join(map(str, positive)).encode()).hexdigest()


class ObserverOptimizationEquivalenceTests(unittest.TestCase):
    def test_scripted_decisions_weights_fallback_random_and_undo_match(self):
        mapping = make_problem()
        events = [[], []]
        old = TracedLegacy(mapping, events[0].append, heuristic="context", seed=7, selection="lexical")
        new = TracedOptimized(mapping, events[1].append, heuristic="context", seed=7, selection="lexical")

        for observer in (old, new):
            # Resolve two cells, abandon the second branch as a conflict would,
            # and then make a replacement decision from restored state.
            observer.on_new_level()
            first = observer.decide()
            observer.on_assignment(first)
            observer.on_new_level()
            second = observer.decide()
            observer.on_assignment(second)
            observer.on_assignment(-(second + 1 if second % 3 else second - 2))
            observer.on_backtrack(1)
            replacement = observer.decide()
            observer.on_assignment(replacement)

        self.assertEqual(old.decision_trace, new.decision_trace)
        self.assertEqual(events[0], events[1])
        self.assertEqual(old.domains, new.domains)
        self.assertEqual(old.selected, new.selected)
        self.assertEqual(old.trails, new.trails)
        self.assertEqual(old.undone_assignments, new.undone_assignments)
        self.assertEqual(new.domain_sizes, [_bit_count(domain) for domain in new.domains])

    def test_event_disabled_mode_changes_only_diagnostic_emission(self):
        mapping = make_problem()
        events = []
        emitting = DomainObserver(
            mapping, events.append, heuristic="context", seed=9, selection="lexical",
        )
        quiet = DomainObserver(
            mapping, lambda event: self.fail("quiet observer emitted an event"),
            heuristic="context", seed=9, selection="lexical", emit_events=False,
        )
        decisions = [[], []]
        for index, observer in enumerate((emitting, quiet)):
            observer.on_new_level()
            decisions[index].append(observer.decide())
            observer.on_assignment(decisions[index][-1])
            observer.on_new_level()
            decisions[index].append(observer.decide())
            observer.on_assignment(decisions[index][-1])
            observer.on_backtrack(1)
            decisions[index].append(observer.decide())
        self.assertTrue(events)
        self.assertEqual(decisions[0], decisions[1])
        self.assertEqual(emitting.domains, quiet.domains)
        self.assertEqual(emitting.domain_sizes, quiet.domain_sizes)
        self.assertEqual(emitting.selected, quiet.selected)
        self.assertEqual(emitting.trails, quiet.trails)
        self.assertEqual(emitting.size_trails, quiet.size_trails)
        self.assertEqual(emitting.undone_assignments, quiet.undone_assignments)

    def test_cadical_conflict_backtrack_trace_and_final_hash_match(self):
        from pysat.solvers import Cadical195

        mapping = make_problem(width=2, height=1)
        patterns = [Pattern(i, ((str(i),),), f) for i, f in zip((10, 11, 12), (3, 2, 1))]
        allowed = {
            "right": {i: [10, 11, 12] for i in (10, 11, 12)},
            "down": {i: [10, 11, 12] for i in (10, 11, 12)},
        }
        cnf = patterns_to_cnf(patterns, allowed, 2, 1, exactly_one_encoding="sequential")
        # Choosing pattern 10 at the first cell forces two mutually exclusive
        # placements at the second cell, producing a genuine CDCL conflict.
        first_10 = cnf.var_map[(0, 0, 10)]
        second_10 = cnf.var_map[(1, 0, 10)]
        second_11 = cnf.var_map[(1, 0, 11)]
        cnf.add_clause([-first_10, second_10])
        cnf.add_clause([-first_10, second_11])

        outcomes = []
        for observer_type in (TracedLegacy, TracedOptimized):
            events = []
            observer = observer_type(
                mapping, events.append, heuristic="context", seed=1, selection="lexical",
            )
            with Cadical195(bootstrap_with=cnf.clauses) as solver:
                solver.connect_propagator(observer)
                for placement in mapping.placements:
                    solver.observe(placement.var)
                sat = solver.solve()
                model = solver.get_model() if sat else []
                stats = solver.accum_stats()
                solver.disconnect_propagator()
            outcomes.append((
                sat, observer.decision_trace, events,
                observer.backtrack_events, observer.undone_assignments,
                placement_hash(model, set(cnf.name_map)),
                stats.get("conflicts", 0),
            ))

        self.assertGreater(outcomes[0][-1], 0)
        self.assertGreater(outcomes[0][3], 0)
        self.assertEqual(outcomes[0], outcomes[1])


if __name__ == "__main__":
    unittest.main()
