# wfc-to-sat

A research compiler for translating overlapping Wave Function Collapse (WFC) constraints into Boolean satisfiability (SAT) instances.

This repository is the clean compiler implementation of the project.

The companion repository `wfc-to-sat-demo` contains visual demonstrations, tutorial branches, experiments, and explanatory material used during development.

---

## Project Goal

Compile procedural generation constraints into DIMACS CNF so that standard SAT solvers can determine whether a generated instance is satisfiable.

Pipeline:

```text
training image or text grid
        ↓
pattern extraction
        ↓
overlap compatibility
        ↓
CNF generation
        ↓
DIMACS output
        ↓
SAT solver
        ↓
SAT / UNSAT result
        ↓
output reconstruction
```

---

## Motivation

Traditional WFC implementations typically rely on propagation, backtracking, restarts, and heuristics.

A SAT-based approach provides a rigorous framework for determining:

```text
SAT
    → a valid output exists

UNSAT
    → no valid output exists
```

By compiling WFC constraints into CNF, the project can leverage modern SAT solvers while retaining the expressive power of overlapping-pattern generation.

---

## Repository Structure

```text
wfc_to_sat/
    patterns.py
    compatibility.py
    cnf.py
    solver.py
    reconstruct.py
    cli.py

examples/
    checkerboard.txt

experiments/
    results.md

tests/
```

---

## Planned Modules

### patterns.py

Extract overlapping patterns from training images and count frequencies.

### compatibility.py

Compute legal overlaps between patterns.

### cnf.py

Generate CNF clauses and DIMACS output.

### solver.py

Interface to MiniSat and other SAT solvers.

### reconstruct.py

Reconstruct output grids from SAT assignments.

### cli.py

Command-line interface for running experiments.

---

## Example Workflow

```text
training image
        ↓
extract patterns
        ↓
compute overlaps
        ↓
generate CNF
        ↓
run MiniSat
        ↓
reconstruct output
```

---

## Example Command

Planned usage:

```bash
python3 -m wfc_to_sat.cli \
    examples/checkerboard.txt \
    --pattern-size 2 \
    --width 20 \
    --height 20
```

Expected outputs:

* CNF file
* SAT / UNSAT result
* reconstructed output
* benchmark statistics

---

## Current Status

This repository is under active development.

The current prototype implementation exists in:

```text
wfc-to-sat-demo
```

The purpose of this repository is to provide a clean, modular compiler suitable for research and eventual publication.

---

## Future Work

* Larger pattern sizes
* Larger output grids
* Real game-development datasets
* Multiple SAT backends
* UNSAT demonstrations
* MaxSAT support
* Performance optimization
* Automated benchmarking
* Artist-friendly tooling

---

## Author

Steve Cross

Research project exploring the compilation of Wave Function Collapse constraints into SAT formulations for procedural content generation.

