# Zelda 3x3 WFC-as-SAT Investigation

## Goal

This investigation targets the paper-compatible overlapping-3x3 Zelda condition: wrapped 3x3 pattern extraction from the authors' map, a 20x20 placement grid with finite/nonperiodic output boundaries, Context-sensitive candidate weighting, seed 0, and WFC-as-SAT. The engineering goal was to make that condition practical while preserving the requested lexical-selection semantics whenever possible. Here, **lexical selection** means choosing the earliest unresolved output cell in row-major order; Context weighting then chooses a pattern using the experiment's source-derived context frequencies.

## Initial feasibility problem

Wrapped extraction produced 2,958 distinct 3x3 patterns. Across 400 output placement cells, that requires 1,183,200 placement variables. The original pairwise at-most-one encoding projected 1,749,361,600 exactly-one clauses and 2,248,080 compatibility/support clauses: about **1,751,609,680 clauses total**. Even counting only Python clause/list containers gave a conservative lower bound of about **130.5 GiB**.

The pairwise formula was therefore not materialized. A safety stop recorded the scale before SAT-variable or CNF allocation; it was plainly impractical in this implementation.

## Sequential exactly-one encoding

An optional Sinz/sequential at-most-one encoding replaced the quadratic pairwise representation for this investigation. The resulting verified formula has:

| Quantity | Count |
| --- | ---: |
| Placement variables | 1,183,200 |
| Auxiliary variables | 1,182,800 |
| Total variables | 2,366,000 |
| Exactly-one clauses | 3,548,400 |
| Support/compatibility clauses | 2,248,080 |
| Total clauses | 5,796,480 |

Pairwise encoding remains available and is still the default where applicable. The sequential representation is semantically equivalent over placement variables: it changes the auxiliary representation, not which pattern assignment is legal at a cell. Exhaustive small-instance CNF tests cover pairwise/sequential equivalence, including satisfiable tilings, decoded solutions, and auxiliary-variable behavior.

## Solver / observer controls

Three controls isolated formula, observer, and WFC-decision costs:

| Configuration | Result |
| --- | --- |
| Plain CaDiCaL | SAT in **0.282540 s** solve time |
| DomainObserver + CaDiCaL decisions | SAT in **22.011392 s** |
| DomainObserver + Context lexical WFC decisions | Timeout, solve **>136.219 s** |

These controls establish that the sequential CNF itself is easy for plain CaDiCaL, that observer tracking adds substantial overhead at this scale, and that the Context-plus-lexical WFC decision trajectory is the dominant observed source of the pathological runtime. They do not isolate every possible interaction or establish a broader causal claim beyond these configurations.

## Profiling and semantics-preserving optimizations

Two optimization stages were committed.

The **decision-path optimization** stopped constructing a full candidate-cell list for lexical selection, precomputed north/east/south/west neighbors, extracted singleton domains directly, safely memoized Context candidate weights, and used precomputed bit masks and set-bit candidate traversal. At matched 10-second profiling checkpoints, overall decision throughput improved by about **1.27x** and `decide()` time per decision improved by about **3.24x**. Cumulative lexical-selection work was about **85.8x lower**, and context-construction work about **214.9x lower**.

The **assignment/domain-maintenance optimization** added backtrack-safe cached domain sizes and an event-disabled mode for experiments whose event callback already discarded every event. The measured assignment callback path was about **1.54x faster**, and repeated domain-size calculation was removed as the identified callback bottleneck.

Equivalence tests passed after both stages. The changes preserve lexical order, Context weights and fallback behavior, ascending candidate order, PRNG sequence, returned SAT literals, and assignment/undo semantics. Tests also compare decision traces, emitted events where enabled, conflict/backtrack behavior, final placement hashes, cached sizes, and quiet versus event-emitting modes.

## Required paper-compatible result

> **Zelda 3x3 · Context weighting · lexical selection · seed 0 · WFC-as-SAT · sequential encoding still TIMES OUT under the 180-second watchdog.**

The latest committed run was terminated with solve time **>138.500730 s**. It produced no model, no generated lexical SAT image, and therefore no four KL values for this required condition. The encoding and observer optimizations did not make the exact paper-compatible run practical within the watchdog.

## Min-entropy diagnostic

Changing only the cell-selection policy from lexical to min-entropy made the Context WFC-as-SAT condition complete. The latest visual checkpoint records SAT in **56.554767 s** solve time (13 conflicts, 228 decisions, and 13 observer backtracks).

**THIS IS A DIAGNOSTIC VARIANT, NOT THE PAPER-COMPATIBLE LEXICAL RESULT.** It demonstrates that cell-selection policy materially changes feasibility; it must not be substituted for the required lexical condition.

## Ordinary WFC visual control

Ordinary WFC with Context weighting, lexical selection, seed 0, and wrapped Zelda overlapping-3x3 patterns completed successfully in **175.440487 s**, with zero contradictions. The checkpoint JSON uses the generic status string `SAT`, but this arm is ordinary WFC—not a SAT-solver run.

## Visual checkpoint

The [committed visual checkpoint](../zelda-3x3-visual-checkpoint/index.html) shows:

- the Zelda source;
- Ordinary WFC — Context — lexical;
- WFC-as-SAT — Context — min-entropy diagnostic; and
- an explicit note that WFC-as-SAT — Context — lexical timed out and has no image.

Both successful outputs passed hard-constraint verification. For both, pattern-edge KL is infinite because the generated output contains pattern-edge events outside the source support. The checkpoint reports that result directly, without smoothing or reinterpretation.

## Current status

- CNF construction/memory blocker: solved with the optional sequential encoding.
- Observer performance: profiled and materially improved in two stages.
- Exact paper-compatible Context + lexical WFC-as-SAT: still impractical under the 180-second watchdog.
- Context + min-entropy WFC-as-SAT diagnostic: feasible.
- Ordinary WFC Context + lexical: feasible but slow.
- Further Zelda 3x3 work remains open.

## Files and commits

Primary evidence and source files:

- [Initial pairwise feasibility JSON](../zelda-3x3/zelda-3x3-context-seed-0.json) and [log](../zelda-3x3/zelda-3x3-context-seed-0-timing.log)
- [Latest sequential lexical result JSON](context-seed-0.json) and [log](context-seed-0-timing.log)
- Controls: [plain CaDiCaL](controls/plain.json) and [observer with solver decisions](controls/observer-solver.json)
- Decision profiles: [before](profile/context-lexical-seed-0.json) and [after](profile-optimized/context-lexical-seed-0.json)
- Assignment profiles: [before](assignment-profile/before-assignment-optimization/context-lexical-seed-0.json) and [after](assignment-profile/after-assignment-optimization/context-lexical-seed-0.json)
- [Visual-checkpoint results](../zelda-3x3-visual-checkpoint/results.json), [HTML](../zelda-3x3-visual-checkpoint/index.html), and [generator](../../../experiments/context_sensitive/zelda_3x3_visual_checkpoint.py)
- [Sequential probe source](../../../experiments/context_sensitive/zelda_3x3_sequential_probe.py), [controls source](../../../experiments/context_sensitive/zelda_3x3_sequential_controls.py), [CNF semantics tests](../../../tests/test_cnf_semantics.py), and [observer equivalence tests](../../../tests/test_observer_optimization_equivalence.py)

Relevant commits:

- `3ffacb1` — Test sequential encoding on Zelda 3x3
- `5972ba7` — Record Zelda 3x3 SAT diagnostics
- `3c17f6b` — Optimize observer context decision hot paths
- `de5e4b6` — Record optimized Zelda 3x3 diagnostics
- `e911781` — Optimize observer assignment domain tracking
- `5a49ce6` — Record Zelda assignment optimization diagnostics
- `e1925f5` — Add Zelda 3x3 visual checkpoint

The branch is `zelda-3x3-sequential-experiment`. This README is a later documentation-only commit and does not change or rerun any experiment.
