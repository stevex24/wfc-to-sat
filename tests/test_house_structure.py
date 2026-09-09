from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

pysat = pytest.importorskip("pysat")
from pysat.solvers import Cadical195

from wfc_to_sat.house_structure import HouseCnf, TileManifest


MANIFEST = Path(__file__).parents[1] / "experiments/tiny_town/manifest.json"


def built(width=8, height=8, minimum=0, maximum=2):
    return HouseCnf(width, height, TileManifest.load(MANIFEST), maximum + 1).build(minimum, maximum)


def sat(cnf, assumptions=()):
    with Cadical195(bootstrap_with=cnf.clauses) as solver:
        ok = solver.solve(assumptions=list(assumptions))
        return solver.get_model() if ok else None


def test_in_definition_both_directions():
    cnf = built()
    x, y = 3, 3
    for tile in cnf.manifest.house_tiles:
        assert sat(cnf, [-cnf.inside(x, y), cnf.assign(x, y, tile)]) is None
    assert sat(cnf, [cnf.inside(x, y), *[-cnf.assign(x, y, t) for t in cnf.manifest.house_tiles]]) is None


def test_ragged_house_is_rejected():
    cnf = built()
    # Adjacent rows overlap at x=3 but disagree at their right boundary.
    assumptions = [cnf.inside(2, 2), cnf.inside(3, 2), -cnf.inside(4, 2),
                   cnf.inside(2, 3), cnf.inside(3, 3), cnf.inside(4, 3)]
    assert sat(cnf, assumptions) is None


def regions(inside):
    height, width = len(inside), len(inside[0])
    unseen = {(x, y) for y in range(height) for x in range(width) if inside[y][x]}
    count = 0
    while unseen:
        count += 1
        todo = deque([unseen.pop()])
        while todo:
            x, y = todo.popleft()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in unseen:
                    unseen.remove(point); todo.append(point)
    return count


def decoded(cnf, model):
    positive = {lit for lit in model if lit > 0}
    inside = [[cnf.inside(x, y) in positive for x in range(cnf.width)] for y in range(cnf.height)]
    anchors = [(x, y) for y in range(cnf.height) for x in range(cnf.width) if cnf.anchor(x, y) in positive]
    return inside, anchors


@pytest.mark.parametrize("seed", range(10))
def test_anchor_count_matches_flood_fill(seed):
    cnf = built(10, 9, 1, 3)
    clauses = list(cnf.clauses)
    __import__("random").Random(seed).shuffle(clauses)
    with Cadical195(bootstrap_with=clauses) as solver:
        assert solver.solve()
        inside, anchors = decoded(cnf, solver.get_model())
    assert regions(inside) == len(anchors)


@pytest.mark.parametrize("seed", range(20))
def test_exactly_three_houses_across_seeds(seed):
    cnf = built(12, 10, 3, 3)
    clauses = list(cnf.clauses)
    __import__("random").Random(seed).shuffle(clauses)
    with Cadical195(bootstrap_with=clauses) as solver:
        assert solver.solve()
        inside, anchors = decoded(cnf, solver.get_model())
    assert len(anchors) == regions(inside) == 3


def test_too_many_houses_is_clean_unsat():
    # A 5x4 map has room for at most one minimum 2x3 house plus its gap.
    cnf = built(5, 4, 2, 2)
    assert sat(cnf) is None


@pytest.mark.parametrize("count", [1, 2, 3])
def test_anchor_count_matches_flood_fill(count):
    cnf = built(12, 10, count, count)
    model = sat(cnf)
    assert model is not None
    positive = {lit for lit in model if lit > 0}
    inside = [[cnf.inside(x, y) in positive for x in range(cnf.width)] for y in range(cnf.height)]
    anchors = sum(cnf.anchor(x, y) in positive for y in range(cnf.height) for x in range(cnf.width))
    assert anchors == regions(inside) == count


@pytest.mark.parametrize("seed", range(10))
def test_exactly_three_houses_many_seeds(seed):
    cnf = built(12, 10, 3, 3)
    clauses = list(cnf.clauses)
    __import__("random").Random(seed).shuffle(clauses)
    with Cadical195(bootstrap_with=clauses) as solver:
        assert solver.solve()
        positive = {lit for lit in solver.get_model() if lit > 0}
    assert sum(cnf.anchor(x, y) in positive for y in range(cnf.height) for x in range(cnf.width)) == 3


def test_impossible_house_request_is_clean_unsat():
    # A 3x4 grid has only one usable house column, while a house needs width >=2.
    cnf = built(3, 4, 1, 1)
    assert sat(cnf) is None


def test_exact_count_counter_outputs_are_assumable():
    cnf = built(12, 10, 1, 4)
    model = sat(cnf, [cnf.counter(cnf.cells, 3), -cnf.counter(cnf.cells, 4)])
    assert model is not None
    positive = {lit for lit in model if lit > 0}
    assert sum(cnf.anchor(x, y) in positive for y in range(cnf.height) for x in range(cnf.width)) == 3
