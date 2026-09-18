"""CNF compiler for structured Kenney Tiny Town houses."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class TileManifest:
    tile_roles: dict[int, str]
    roles: dict[str, tuple[int, ...]]
    house_tiles: frozenset[int]
    style_family: dict[int, str]
    door_tiles: frozenset[int]
    door_opening_tiles: frozenset[int]
    roof_gable_edge_tiles: frozenset[int]

    @classmethod
    def load(cls, path: str | Path) -> "TileManifest":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        roles = {name: tuple(map(int, ids)) for name, ids in value["tiles"].items()}
        tile_roles = {tile: role for role, ids in roles.items() for tile in ids}
        if len(tile_roles) != sum(map(len, roles.values())):
            raise ValueError("a tile occurs in more than one manifest role")
        house = frozenset(tile for role in value["house_roles"] for tile in roles[role])
        style_family = {tile: name for name, ids in value.get("style_families", {}).items() for tile in ids}
        if any(tile not in style_family for tile in house):
            raise ValueError("every house tile needs a style family")
        doors = frozenset(value.get("door_tiles", ()))
        openings = frozenset(value.get("door_opening_tiles", ()))
        if not doors or not doors <= set(roles["body_inside"]):
            raise ValueError("door tiles must be body interiors")
        if not openings <= set(roles["body_inside"]) or doors & openings:
            raise ValueError("door openings must be separate body interiors")
        edges = frozenset(value.get("roof_gable_edge_tiles", ()))
        if not edges <= set(roles["roof_top_inside"] + roles["roof_inside"]):
            raise ValueError("gable-edge tiles must be roof interiors")
        return cls(tile_roles, roles, house, style_family, doors, openings, edges)


class HouseCnf:
    """A deterministic block allocator plus a DIMACS clause store."""

    def __init__(self, width: int, height: int, manifest: TileManifest, counter_limit: int):
        if width < 3 or height < 4:
            raise ValueError("house maps need width >= 3 and height >= 4")
        self.width, self.height, self.manifest = width, height, manifest
        self.tiles = tuple(sorted(manifest.tile_roles))
        self.tile_index = {tile: index for index, tile in enumerate(self.tiles)}
        self.cells, self.counter_limit = width * height, counter_limit
        self.assign_base = 1
        self.in_base = self.assign_base + self.cells * len(self.tiles)
        self.anchor_base = self.in_base + self.cells
        self.counter_base = self.anchor_base + self.cells
        self.next_var = self.counter_base + self.cells * counter_limit
        self.door_seen_base = self.next_var
        self.next_var += self.cells
        self.clauses: list[list[int]] = []

    @property
    def num_vars(self) -> int:
        return self.next_var - 1

    def assign(self, x: int, y: int, tile: int) -> int:
        return self.assign_base + (y * self.width + x) * len(self.tiles) + self.tile_index[tile]

    def inside(self, x: int, y: int) -> int:
        return self.in_base + y * self.width + x

    def anchor(self, x: int, y: int) -> int:
        return self.anchor_base + y * self.width + x

    def counter(self, prefix: int, count: int) -> int:
        """prefix is 1..cells and count is 1..counter_limit."""
        return self.counter_base + (prefix - 1) * self.counter_limit + count - 1

    def door_seen(self, x: int, y: int) -> int:
        """Whether the current body row has seen a door since its left edge."""
        return self.door_seen_base + y * self.width + x

    def add(self, *lits: int) -> None:
        self.clauses.append(list(lits))

    def build(self, min_houses: int, max_houses: int) -> "HouseCnf":
        if not 0 <= min_houses <= max_houses < self.counter_limit:
            raise ValueError("bounds require 0 <= min <= max < counter_limit")
        self._exactly_one_tiles()
        self._define_inside()
        self._house_grammar()
        self._doors()
        self._equal_width()
        self._define_anchors()
        self._define_counter()
        if min_houses:
            self.add(self.counter(self.cells, min_houses))
        self.add(-self.counter(self.cells, max_houses + 1))
        return self

    def _exactly_one_tiles(self) -> None:
        for y in range(self.height):
            for x in range(self.width):
                variables = [self.assign(x, y, tile) for tile in self.tiles]
                self.clauses.append(variables)
                for i, left in enumerate(variables):
                    for right in variables[i + 1:]:
                        self.add(-left, -right)

    def _define_inside(self) -> None:
        for y in range(self.height):
            for x in range(self.width):
                inside = self.inside(x, y)
                houses = [self.assign(x, y, tile) for tile in sorted(self.manifest.house_tiles)]
                self.clauses.append([-inside, *houses])
                for variable in houses:
                    self.add(-variable, inside)

    def _house_grammar(self) -> None:
        r = self.manifest.roles
        left = set(r["roof_top_left"] + r["roof_left"] + r["body_left"])
        middle = set(r["roof_top_inside"] + r["roof_inside"] + r["body_inside"])
        right = set(r["roof_top_right"] + r["roof_right"] + r["body_right"])
        top, roof = set(r["roof_top_left"] + r["roof_top_inside"] + r["roof_top_right"]), set(r["roof_left"] + r["roof_inside"] + r["roof_right"])
        body, ground = set(r["body_left"] + r["body_inside"] + r["body_right"]), set(r["ground"])

        def styled(tile: int, candidates: set[int]) -> set[int]:
            if tile in ground:
                return candidates
            family = self.manifest.style_family[tile]
            return {candidate for candidate in candidates
                    if candidate in ground or self.manifest.style_family.get(candidate) == family}

        # Horizontal rows are L M+ R; edge house tiles are forbidden.
        for y in range(self.height):
            for x in range(self.width):
                for tile in self.tiles:
                    var = self.assign(x, y, tile)
                    all_tiles = set(self.tiles)
                    allowed_left = all_tiles if tile in ground else (ground if tile in left else left | middle)
                    allowed_right = all_tiles if tile in ground else (ground if tile in right else middle | right)
                    # The last roof-interior sprite has a dark right edge. It
                    # belongs immediately before the gable, never mid-roof.
                    if tile in self.manifest.roof_gable_edge_tiles:
                        allowed_right &= right
                    if tile not in ground:
                        if tile in top:
                            allowed_left &= ground | top
                            allowed_right &= ground | top
                        elif tile in roof:
                            allowed_left &= ground | roof
                            allowed_right &= ground | roof
                        else:
                            allowed_left &= ground | body
                            allowed_right &= ground | body
                    allowed_left, allowed_right = styled(tile, allowed_left), styled(tile, allowed_right)
                    if x == 0 and tile not in ground: self.add(-var)
                    elif x > 0: self.clauses.append([-var, *[self.assign(x - 1, y, t) for t in allowed_left]])
                    if x == self.width - 1 and tile not in ground: self.add(-var)
                    elif x + 1 < self.width: self.clauses.append([-var, *[self.assign(x + 1, y, t) for t in allowed_right]])

        # A house is top roof, 1..3 lower-roof rows, then >=1 body row.
        for y in range(self.height):
            for x in range(self.width):
                for tile in self.tiles:
                    var = self.assign(x, y, tile)
                    if tile in top:
                        if y == 0: pass
                        else: self.clauses.append([-var, *[self.assign(x, y - 1, t) for t in ground]])
                        if y + 1 >= self.height: self.add(-var)
                        else: self.clauses.append([-var, *[self.assign(x, y + 1, t) for t in styled(tile, roof)]])
                    elif tile in roof:
                        if y == 0: self.add(-var)
                        else: self.clauses.append([-var, *[self.assign(x, y - 1, t) for t in styled(tile, top | roof)]])
                        if y + 1 >= self.height: self.add(-var)
                        else: self.clauses.append([-var, *[self.assign(x, y + 1, t) for t in styled(tile, roof | body)]])
                    elif tile in body:
                        if y == 0: self.add(-var)
                        else: self.clauses.append([-var, *[self.assign(x, y - 1, t) for t in styled(tile, roof | body)]])
                        if y + 1 < self.height:
                            self.clauses.append([-var, *[self.assign(x, y + 1, t) for t in styled(tile, body | ground)]])
        # No run of four lower-roof cells: the roof depth is at most three.
        for y in range(self.height - 3):
            for x in range(self.width):
                for choices in _product_vars(self, x, range(y, y + 4), roof):
                    self.clauses.append([-v for v in choices])

    def _doors(self) -> None:
        r = self.manifest.roles
        ground = set(r["ground"])
        body_right = set(r["body_right"])
        body_middle = set(r["body_inside"])
        doors = set(self.manifest.door_tiles)
        openings = set(self.manifest.door_opening_tiles)
        for y in range(self.height):
            for x in range(self.width):
                seen = self.door_seen(x, y)
                door_vars = [self.assign(x, y, t) for t in doors]
                middle_vars = [self.assign(x, y, t) for t in body_middle]
                # seen <-> door here OR (body interior here AND seen left).
                for door in door_vars:
                    self.add(-door, seen)
                if x:
                    previous = self.door_seen(x - 1, y)
                    for middle in middle_vars:
                        self.add(-middle, -previous, seen)
                    self.clauses.append([-seen, *door_vars, previous])
                    self.clauses.append([-seen, *middle_vars])
                else:
                    self.clauses.append([-seen, *door_vars])
                for door in door_vars:
                    if y + 1 < self.height:
                        self.clauses.append([-door, *[self.assign(x, y + 1, t) for t in ground]])
                # An open doorway is the upper half of a door and must align.
                for opening in openings:
                    if y + 1 == self.height:
                        self.add(-self.assign(x, y, opening))
                    else:
                        family = self.manifest.style_family[opening]
                        matching = [t for t in doors if self.manifest.style_family[t] == family]
                        self.clauses.append([-self.assign(x, y, opening),
                                             *[self.assign(x, y + 1, t) for t in matching]])
                # A bottom body row must contain a door before its right edge.
                for right in body_right:
                    end = self.assign(x, y, right)
                    if x == 0:
                        continue
                    if y + 1 == self.height:
                        self.add(-end, self.door_seen(x - 1, y))
                    else:
                        for tile in ground:
                            self.add(-end, -self.assign(x, y + 1, tile),
                                     self.door_seen(x - 1, y))

    def _equal_width(self) -> None:
        for y in range(self.height - 1):
            for x in range(self.width):
                here, below = self.inside(x, y), self.inside(x, y + 1)
                for nx in (x - 1, x + 1):
                    if 0 <= nx < self.width:
                        side, side_below = self.inside(nx, y), self.inside(nx, y + 1)
                        self.add(-here, -below, -side, side_below)
                        self.add(-here, -below, -side_below, side)

    def _define_anchors(self) -> None:
        for y in range(self.height):
            for x in range(self.width):
                a, inside = self.anchor(x, y), self.inside(x, y)
                self.add(-a, inside)
                if x: self.add(-a, -self.inside(x - 1, y))
                if y: self.add(-a, -self.inside(x, y - 1))
                reverse = [a, -inside]
                if x: reverse.append(self.inside(x - 1, y))
                if y: reverse.append(self.inside(x, y - 1))
                self.clauses.append(reverse)

    def _define_counter(self) -> None:
        # s(i,j) <-> at least j anchors among the first i cells.
        for i in range(1, self.cells + 1):
            a = self.anchor((i - 1) % self.width, (i - 1) // self.width)
            for j in range(1, self.counter_limit + 1):
                s = self.counter(i, j)
                prev = self.counter(i - 1, j) if i > 1 else None
                prev_lower = self.counter(i - 1, j - 1) if i > 1 and j > 1 else None
                if j > i:
                    self.add(-s)
                    continue
                # (prev OR (a AND prev_lower)), with prev_lower=True for j=1.
                if j == 1:
                    self.clauses.append([-s, *([prev] if prev else []), a])
                else:
                    self.clauses.append([-s, *([prev] if prev else []), a])
                    self.clauses.append([-s, *([prev] if prev else []), prev_lower])
                if prev: self.add(-prev, s)
                if j == 1: self.add(-a, s)
                else: self.add(-a, -prev_lower, s)

    def dimacs(self) -> str:
        rows = [f"p cnf {self.num_vars} {len(self.clauses)}"]
        rows += [" ".join(map(str, clause)) + " 0" for clause in self.clauses]
        return "\n".join(rows) + "\n"

    def structural_mapping(self) -> dict:
        return {
            "blocks": {
                "assign": {"first": self.assign_base, "last": self.in_base - 1, "formula": "first + (y*W+x)*T + tile_index"},
                "in": {"first": self.in_base, "last": self.anchor_base - 1, "formula": "first + y*W+x"},
                "anchor": {"first": self.anchor_base, "last": self.counter_base - 1, "formula": "first + y*W+x"},
                "counter": {"first": self.counter_base, "last": self.door_seen_base - 1, "formula": "first + (prefix-1)*K + count-1"},
                "door_seen": {"first": self.door_seen_base, "last": self.num_vars, "formula": "first + y*W+x"}
            },
            "in": [{"var": self.inside(x, y), "x": x, "y": y} for y in range(self.height) for x in range(self.width)],
            "anchor": [{"var": self.anchor(x, y), "x": x, "y": y} for y in range(self.height) for x in range(self.width)],
            "counter": [{"var": self.counter(i, j), "prefix": i, "count": j, "output": i == self.cells} for i in range(1, self.cells + 1) for j in range(1, self.counter_limit + 1)],
            "outputs": {str(j): self.counter(self.cells, j) for j in range(1, self.counter_limit + 1)}
        }


def _product_vars(cnf: HouseCnf, x: int, ys: Iterable[int], tiles: set[int]):
    # Yielding the Cartesian product keeps the four-cell forbidden relation in CNF.
    import itertools
    pools = [[cnf.assign(x, y, tile) for tile in tiles] for y in ys]
    yield from itertools.product(*pools)
