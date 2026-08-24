"""Shared mapping and trace helpers for the CDCL visualizer."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO


TRACE_VERSION = 1
MAPPING_VERSION = 2


@dataclass(frozen=True)
class PatternSpec:
    id: int
    frequency: int
    width: int
    height: int
    rgba: bytes

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "PatternSpec":
        try:
            rgba = base64.b64decode(value["rgba"], validate=True)
            result = cls(
                id=int(value["id"]),
                frequency=int(value["frequency"]),
                width=int(value["width"]),
                height=int(value["height"]),
                rgba=rgba,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid pattern record: {value!r}") from error
        if result.frequency <= 0:
            raise ValueError(f"pattern {result.id} frequency must be positive")
        if result.width <= 0 or result.height <= 0:
            raise ValueError(f"pattern {result.id} dimensions must be positive")
        if len(result.rgba) != result.width * result.height * 4:
            raise ValueError(f"pattern {result.id} RGBA byte count is incorrect")
        return result

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "frequency": self.frequency,
            "width": self.width,
            "height": self.height,
            "rgba": base64.b64encode(self.rgba).decode("ascii"),
        }


@dataclass(frozen=True)
class Placement:
    var: int
    x: int
    y: int
    pattern_id: int


@dataclass(frozen=True)
class MappingSpec:
    width: int
    height: int
    patterns: tuple[PatternSpec, ...]
    placements: tuple[Placement, ...]
    compatibility: dict[str, dict[int, tuple[int, ...]]] | None = None
    source_pattern_grid: tuple[tuple[int, ...], ...] | None = None

    @classmethod
    def load(cls, path: str | Path, num_vars: int | None = None) -> "MappingSpec":
        with Path(path).open(encoding="utf-8") as stream:
            value = json.load(stream)
        try:
            grid = value["grid"]
            width, height = int(grid["width"]), int(grid["height"])
            patterns = tuple(PatternSpec.from_json(item) for item in value["patterns"])
            placements = tuple(
                Placement(int(item["var"]), int(item["x"]), int(item["y"]), int(item["pattern_id"]))
                for item in value["variables"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("mapping sidecar has an invalid shape") from error
        version = int(value.get("mapping_version", 1))
        if version not in (1, MAPPING_VERSION):
            raise ValueError(f"unsupported mapping version {version}")
        if value.get("context_data") is not None and version != MAPPING_VERSION:
            raise ValueError("context_data requires mapping version 2")
        compatibility = _parse_compatibility(value.get("compatibility"))
        source_pattern_grid = _parse_source_pattern_grid(value.get("context_data"))
        result = cls(width, height, patterns, placements, compatibility, source_pattern_grid)
        result.validate(num_vars=num_vars)
        return result

    def validate(self, num_vars: int | None = None) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("grid dimensions must be positive")
        ids = [pattern.id for pattern in self.patterns]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("pattern IDs must be non-empty and unique")
        id_set = set(ids)
        variables: set[int] = set()
        triples: set[tuple[int, int, int]] = set()
        cells: dict[tuple[int, int], set[int]] = {}
        for item in self.placements:
            if item.var <= 0 or (num_vars is not None and item.var > num_vars):
                raise ValueError(f"placement variable {item.var} is outside the CNF range")
            if item.var in variables:
                raise ValueError(f"duplicate placement variable {item.var}")
            if not (0 <= item.x < self.width and 0 <= item.y < self.height):
                raise ValueError(f"placement variable {item.var} has out-of-bounds coordinates")
            if item.pattern_id not in id_set:
                raise ValueError(f"placement variable {item.var} references an unknown pattern")
            triple = (item.x, item.y, item.pattern_id)
            if triple in triples:
                raise ValueError(f"duplicate placement mapping {triple}")
            variables.add(item.var)
            triples.add(triple)
            cells.setdefault((item.x, item.y), set()).add(item.pattern_id)
        expected = {(x, y) for y in range(self.height) for x in range(self.width)}
        if set(cells) != expected or any(patterns != id_set for patterns in cells.values()):
            raise ValueError("every cell must map exactly once to every pattern")
        dimensions = {(pattern.width, pattern.height) for pattern in self.patterns}
        if len(dimensions) != 1:
            raise ValueError("all pattern pixel tiles must have the same dimensions")
        if self.compatibility is not None:
            for direction, table in self.compatibility.items():
                if set(table) != id_set:
                    raise ValueError(f"compatibility.{direction} must define every pattern")
                for pattern_id, compatible in table.items():
                    if not set(compatible) <= id_set:
                        raise ValueError(f"compatibility.{direction}.{pattern_id} references an unknown pattern")
        if self.source_pattern_grid is not None:
            if not self.source_pattern_grid or not self.source_pattern_grid[0]:
                raise ValueError("source pattern grid must be nonempty")
            source_width = len(self.source_pattern_grid[0])
            if any(len(row) != source_width for row in self.source_pattern_grid):
                raise ValueError("source pattern grid must be rectangular")
            if any(item not in id_set for row in self.source_pattern_grid for item in row):
                raise ValueError("source pattern grid references an unknown pattern")
            counts = Counter(item for row in self.source_pattern_grid for item in row)
            frequencies = {pattern.id: pattern.frequency for pattern in self.patterns}
            if counts != frequencies:
                raise ValueError("source pattern occurrences must match pattern frequencies")

    def header(self, run: dict[str, Any]) -> dict[str, Any]:
        value: dict[str, Any] = {
            "type": "header",
            "version": TRACE_VERSION,
            "grid": {"width": self.width, "height": self.height},
            "patterns": [item.to_json() for item in self.patterns],
            "variables": [
                [item.var, item.x, item.y, item.pattern_id] for item in self.placements
            ],
            "run": run,
            "capabilities": {"learned_clause_cells": False},
        }
        if self.compatibility is not None:
            value["compatibility"] = {
                direction: {str(key): list(items) for key, items in table.items()}
                for direction, table in self.compatibility.items()
            }
        if self.source_pattern_grid is not None:
            value["mapping_version"] = MAPPING_VERSION
            value["context_data"] = {
                "kind": "source-pattern-occurrences",
                "boundary": "unknown",
                "grid": [list(row) for row in self.source_pattern_grid],
            }
        return value

    def to_json(self) -> dict[str, Any]:
        """Return the validated, versioned mapping sidecar representation."""
        value = self.header({})
        value.pop("type")
        value.pop("version")
        value.pop("run")
        value.pop("capabilities")
        value["variables"] = [
            {"var": item.var, "x": item.x, "y": item.y, "pattern_id": item.pattern_id}
            for item in self.placements
        ]
        return value


def _parse_compatibility(value: Any) -> dict[str, dict[int, tuple[int, ...]]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("compatibility must be an object")
    result: dict[str, dict[int, tuple[int, ...]]] = {}
    for direction in ("right", "down"):
        table = value.get(direction)
        if not isinstance(table, dict):
            raise ValueError(f"compatibility.{direction} must be an object")
        result[direction] = {int(key): tuple(int(item) for item in items) for key, items in table.items()}
    return result


def _parse_source_pattern_grid(value: Any) -> tuple[tuple[int, ...], ...] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("kind") != "source-pattern-occurrences":
        raise ValueError("context_data must contain source pattern occurrences")
    if value.get("boundary") != "unknown":
        raise ValueError("context_data boundary must be 'unknown'")
    grid = value.get("grid")
    if not isinstance(grid, list) or not all(isinstance(row, list) for row in grid):
        raise ValueError("context_data.grid must be an array of arrays")
    try:
        return tuple(tuple(int(item) for item in row) for row in grid)
    except (TypeError, ValueError) as error:
        raise ValueError("context_data.grid contains a non-integer pattern ID") from error


def open_trace(path: str | Path, mode: str) -> TextIO:
    trace_path = Path(path)
    if "b" in mode:
        raise ValueError("trace helpers use text mode")
    if trace_path.suffix == ".gz":
        return gzip.open(trace_path, mode, encoding="utf-8")
    return trace_path.open(mode, encoding="utf-8")


class TraceWriter:
    def __init__(self, stream: TextIO):
        self.stream = stream
        self.count = 0

    def write(self, event: Any) -> None:
        self.stream.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.count += 1

    def flush(self) -> None:
        self.stream.flush()


def read_trace(path: str | Path) -> Iterator[Any]:
    with open_trace(path, "rt") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid trace JSON on line {line_number}") from error


def clauses_satisfied(clauses: Iterable[Iterable[int]], model: Iterable[int]) -> bool:
    positive = {literal for literal in model if literal > 0}
    return all(any((lit > 0 and lit in positive) or (lit < 0 and -lit not in positive) for lit in clause) for clause in clauses)
