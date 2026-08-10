#!/usr/bin/env python3
"""Solve a DIMACS instance with CaDiCaL and record domain-level events."""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys
from typing import Iterable

from observer import DomainObserver
from trace_format import MappingSpec, TraceWriter, clauses_satisfied, open_trace


def read_dimacs(path: str | Path) -> tuple[int, list[list[int]]]:
    num_vars: int | None = None
    declared_clauses: int | None = None
    clauses: list[list[int]] = []
    pending: list[int] = []
    with Path(path).open(encoding="ascii") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            line = raw_line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                fields = line.split()
                if len(fields) != 4 or fields[1] != "cnf" or num_vars is not None:
                    raise ValueError(f"invalid DIMACS header on line {line_number}")
                num_vars, declared_clauses = int(fields[2]), int(fields[3])
                continue
            if num_vars is None:
                raise ValueError("DIMACS clauses precede the header")
            for token in line.split():
                literal = int(token)
                if literal == 0:
                    clauses.append(pending)
                    pending = []
                else:
                    if abs(literal) > num_vars:
                        raise ValueError(f"literal {literal} exceeds declared variable count")
                    pending.append(literal)
    if num_vars is None or declared_clauses is None:
        raise ValueError("DIMACS header is missing")
    if pending:
        raise ValueError("unterminated DIMACS clause")
    if len(clauses) != declared_clauses:
        raise ValueError(f"DIMACS declares {declared_clauses} clauses but contains {len(clauses)}")
    return num_vars, clauses


def parse_option(value: str) -> tuple[str, int]:
    try:
        name, raw_value = value.split("=", 1)
        if not name or not name.replace("_", "").isalnum():
            raise ValueError
        return name, int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("CaDiCaL options must use NAME=INTEGER") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--heuristic", choices=("wfc", "solver"), default="solver")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--solver", choices=("cadical195",), default="cadical195")
    parser.add_argument("--watchable", action="store_true", help="use a longer restart interval")
    parser.add_argument("--cadical-option", action="append", default=[], type=parse_option, metavar="NAME=VALUE")
    return parser


def solve(args: argparse.Namespace) -> bool:
    try:
        import pysat
        from pysat.solvers import Cadical195
    except ImportError as error:
        raise RuntimeError("PySAT is required; install dependencies with 'python -m pip install -r requirements.txt'") from error

    num_vars, clauses = read_dimacs(args.cnf)
    mapping = MappingSpec.load(args.mapping, num_vars=num_vars)
    options: dict[str, int] = {"restartint": 100} if args.watchable else {}
    options.update(dict(args.cadical_option))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with open_trace(args.output, "wt") as stream:
        writer = TraceWriter(stream)
        run = {
            "cnf": args.cnf.name,
            "mapping": args.mapping.name,
            "heuristic": args.heuristic,
            "seed": args.seed,
            "solver": args.solver,
            "pysat_version": getattr(pysat, "__version__", "unknown"),
            "python": platform.python_version(),
            "cadical_options": options,
        }
        writer.write(mapping.header(run))
        observer = DomainObserver(mapping, writer.write, heuristic=args.heuristic, seed=args.seed)
        try:
            with Cadical195(bootstrap_with=clauses, use_timer=True) as solver:
                required = ("connect_propagator", "observe", "configure", "accum_stats")
                missing = [name for name in required if not hasattr(solver, name)]
                if missing:
                    raise RuntimeError(f"installed PySAT lacks required IPASIR-UP methods: {', '.join(missing)}")
                if options:
                    solver.configure(options)
                solver.connect_propagator(observer)
                for placement in mapping.placements:
                    solver.observe(placement.var)
                result = solver.solve()
                stats = solver.accum_stats()
                stats["time_seconds"] = solver.time()
                model: list[int] = []
                if result:
                    model = solver.get_model() or []
                    if not observer.check_model(model):
                        raise RuntimeError("CaDiCaL returned a model with invalid cell assignments")
                    if not clauses_satisfied(clauses, model):
                        raise RuntimeError("CaDiCaL returned a model that does not satisfy the DIMACS clauses")
                # CaDiCaL backtracks while disconnecting/destroying a solved
                # instance. That is lifecycle cleanup, not part of the search.
                observer.emit = lambda event: None
                solver.disconnect_propagator()
                if result:
                    writer.write(["m"])
                    writer.write(["e", "sat", stats])
                else:
                    writer.write(["e", "unsat", stats])
                writer.flush()
                return bool(result)
        except Exception as error:
            writer.write(["e", "error", {"message": str(error)}])
            writer.flush()
            raise


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        satisfiable = solve(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"solve_trace: {error}", file=sys.stderr)
        return 2
    print(f"{'SAT' if satisfiable else 'UNSAT'}; wrote {args.output}")
    return 0 if satisfiable else 1


if __name__ == "__main__":
    raise SystemExit(main())
