# WFC-to-SAT Context-Sensitive Heuristics and Benchmark Experiment

I want to extend my existing **wfc-to-sat** research project to implement and experimentally compare context-sensitive WFC decision heuristics in ordinary WFC and in the SAT-plugin version.

The existing repository is:

[https://github.com/stevex24/wfc-to-sat](https://github.com/stevex24/wfc-to-sat)

I am also attaching the paper:

**Bahar Bateni, Isaac Karth, and Adam M. Smith, “Better Resemblance without Bigger Patterns: Making Context-sensitive Decisions in WFC.”**

This prompt is the authoritative specification for the new work. It incorporates an earlier experiment-design document and methodological discussion, so you do not need those earlier documents.

The overall goals are:

1. Preserve the existing working WFC-to-SAT implementation.
2. Create a new Git branch for this experiment.
3. Implement the paper's context-sensitive decision heuristic in ordinary WFC and through the SAT-plugin mechanism.
4. Determine experimentally whether WFC-style heuristics implemented through SAT reproduce the statistical behavior of their ordinary-WFC counterparts.
5. Compare output resemblance, long-range spatial structure, execution time, and memory use.
6. Apply the validated methods to the existing WFC-to-SAT benchmark images.
7. Provide a reproducible one-command shell-script workflow.

# 0. CRITICAL VERSION-CONTROL REQUIREMENT

Before modifying **any code**, inspect the repository and Git state.

The public repository currently appears to use `main` as its primary branch, but **do not assume blindly that** **`main`** **is the correct experimental baseline**.

First:

1. clone/fetch the repository if necessary;
2. run `git status`;
3. identify the current branch;
4. list local and remote branches;
5. inspect recent commit history;
6. identify staged changes;
7. identify unstaged changes;
8. identify relevant untracked files;
9. determine which branch/commit contains the latest working SAT-vs-WFC comparison implementation.

The baseline we want is the latest working version containing the existing WFC/SAT comparison system, including such components as:

- `compare_sat_wfc.sh`
- `observer.py`
- `solve_trace.py`
- `trace_format.py`
- the `wfc_to_sat/` package
- existing tests
- existing experiment support.

The repository currently documents `compare_sat_wfc.sh` as the SAT/CDCL-vs-WFC comparison entry point.

If `main` contains the latest intended working implementation, use `main` as the baseline.

If another existing branch clearly contains later relevant work, **do not guess**. Explain what you found and ask me before choosing it as the baseline.

Record the exact baseline commit hash.

## Protect Existing Work

Do not modify the baseline branch.

Do not overwrite or delete existing working code, benchmark scripts, results, or inputs.

If the working tree contains uncommitted changes, **do not automatically commit, stash, discard, reset, clean, or otherwise alter them**.

Instead, report exactly what you found and ask me how I want to preserve them.

If the baseline is clean and established, create a new branch:

`context-sensitive-experiments`

from that exact baseline commit.

If that branch already exists, do not overwrite it. Report what it contains and use an appropriate unused branch name only after establishing what happened.

All new work described below must occur on the experimental branch.

Do not merge it into the baseline branch unless I explicitly request that later.

# 1. PRESERVE THE EXISTING REPRODUCIBLE BASELINE

The repository already contains a SAT-vs-WFC comparison workflow.

Preserve it.

In particular, do not simply replace `compare_sat_wfc.sh`.

Create a new experiment driver where practical, for example:

`run_context_sensitive_experiments.sh`

Reuse existing modules/functions when appropriate, but preserve the previous entry point so the earlier experiment remains reproducible.

Likewise:

- do not overwrite old result CSVs;
- do not overwrite old plots;
- do not overwrite old generated images;
- do not modify original benchmark images;
- do not reuse result directories destructively.

Use experiment-specific output directories.

# 2. EXISTING BENCHMARK INPUTS

The repository currently documents these supplied image examples:

- `examples/simple-knot.png`
- `examples/cat.png`
- `examples/chess.png`
- `examples/knot.png`
- `examples/simple-maze.png`
- `examples/simple-wall.png`

The existing SAT-vs-WFC workflow currently documents defaults of pattern size `N=3` and an `8x8` placement grid.

Verify all of this against the checked-out baseline rather than assuming the README is perfectly synchronized with the implementation.

The first scientific validation experiments, however, should use the **Stick and Zelda examples from the attached Better Resemblance paper** before applying the method to this existing benchmark suite.

# 3. IMPORTANT TERMINOLOGY

Distinguish carefully between:

- **selection heuristic**: which unresolved location is selected next;
- **decision heuristic**: which tile/pattern is selected at that location.

The *Better Resemblance* context-sensitive modification is principally a **decision heuristic**.

Do not call it a selection heuristic merely because earlier project notes sometimes used that terminology.

Use the distinction consistently in:

- code;
- CLI names;
- tables;
- documentation;
- plots;
- discussion.

This distinction is scientifically important because location-selection order may itself affect context availability and spatial anisotropy.

# 4. INSPECT THE EXISTING IMPLEMENTATION BEFORE CHANGING IT

Before implementing anything, determine exactly how the current repository handles:

- pattern extraction;
- pattern frequencies;
- overlap compatibility;
- CNF construction;
- reconstruction;
- ordinary WFC propagation;
- ordinary WFC location selection;
- ordinary WFC tile/pattern decisions;
- SAT/CDCL decisions;
- SAT observer/plugin behavior;
- WFC-style SAT-plugin decisions;
- randomness and random seeds;
- propagation;
- conflicts;
- backtracking;
- undo state;
- contradiction handling;
- output reconstruction;
- trace generation;
- timing;
- existing benchmarks.

Do not redesign the system from scratch.

Prefer the smallest clean extension of the current implementation.

# 5. HEURISTICS / ENGINE CONDITIONS

Ultimately support these experimental conditions where scientifically meaningful.

## Ordinary WFC

1. Uniform decision heuristic.
2. Classic WFC frequency-weighted decision heuristic.
3. Context-sensitive decision heuristic from *Better Resemblance*.

## SAT engine

1. Plain SAT/CDCL solver behavior.
2. Uniform WFC-like decision heuristic through the SAT plugin.
3. Classic WFC frequency-weighted decision heuristic through the SAT plugin.
4. Context-sensitive decision heuristic through the SAT plugin.

The central scientific question is not merely whether these programs generate valid outputs.

It is:

**Do corresponding WFC and SAT-plugin heuristics produce the same statistical distribution of outputs, or does embedding WFC-style decisions inside SAT/CDCL systematically change the resulting generator?**

# 6. IMPLEMENT THE BETTER RESEMBLANCE CONTEXT-SENSITIVE METHOD FAITHFULLY

For candidate tile/pattern `x` at selected location and currently observed context `c`, use decision weight proportional to:

`freq(x, c)`

rather than ordinary:

`freq(x)`.

The context consists of already-decided immediate neighbors, using an `UNK` representation for neighbors that have not yet been decided.

Implement the source preprocessing needed to count the masked context variants described in the paper.

For a two-dimensional four-neighbor context, account for the paper's masked combinations of known and unknown neighbors.

If all legal candidate tiles/patterns have zero frequency for the observed context, fall back to ordinary source-frequency weighting, as specified in the paper.

Do not silently substitute a different context-sensitive heuristic.

# 7. SAT BACKTRACKING IS A SPECIAL CORRECTNESS RISK

The SAT-plugin context-sensitive implementation must remain correct across:

- decisions;
- propagation;
- conflicts;
- learned clauses where relevant;
- backtracking;
- undo;
- repeated solving.

Context must represent the appropriate currently established neighboring states, not stale decisions from a branch that SAT has already undone.

Add tests specifically for this.

A visually plausible generated image is not sufficient evidence of correctness.

# 8. OVERLAPPING 3x3 PATTERNS

The paper also evaluates overlapping 3x3 WFC.

Before implementing the context-sensitive 3x3 case, explain how the paper maps onto this repository's overlapping-pattern representation.

Explicitly identify:

1. what `x` represents;
2. what `c` represents;
3. what `freq(x,c)` counts;
4. how neighboring pattern identities are represented;
5. how overlapping constraints interact with the context;
6. how final tiles are reconstructed;
7. how our implementation corresponds to the paper's 3x3 experiment.

Do not silently guess if there is ambiguity.

# 9. FIRST VALIDATION QUESTION: DOES WFC-AS-SAT ACTUALLY MATCH WFC?

Before large experiments, compare:

- Uniform WFC vs Uniform-as-SAT;
- Frequency-weighted WFC vs Frequency-weighted-as-SAT;
- Context-sensitive WFC vs Context-sensitive-as-SAT.

Exact individual outputs need not match.

The question is whether the resulting distributions are statistically consistent.

Control as many factors as possible:

- input data;
- output size;
- pattern extraction;
- adjacency rules;
- boundary conditions;
- wrapping;
- selection heuristic;
- decision probabilities;
- seeds;
- contradiction policy;
- backtracking policy.

If SAT/CDCL inherently prevents exact semantic equivalence on some dimension, identify that explicitly.

Do not label an implementation mismatch as a scientific result.

# 10. PRIMARY PAPER-STYLE EXPERIMENTS

Use the experimental structure of *Better Resemblance*.

For primary quantitative experiments use:

- **100 generated outputs**
- **20x20 output size**

Run:

## Stick

- Uniform WFC
- Uniform-as-SAT
- Plain SAT
- Frequency-weighted WFC
- Frequency-weighted-as-SAT
- Context-sensitive WFC
- Context-sensitive-as-SAT

## Zelda 1x1

Run the same applicable conditions.

## Zelda overlapping 3x3

Run the same applicable conditions.

# 11. PRIMARY RESEMBLANCE METRICS

Calculate at least:

1. tile/pattern-frequency resemblance;
2. edge-frequency resemblance.

Use the same KL-divergence direction, normalization, support/domain convention, and pooling convention as the paper when reproducing the paper's numbers.

Attempt to reproduce or approximately reproduce the published ordinary-WFC results before interpreting SAT differences.

A substantial failure to reproduce the paper should be investigated rather than ignored.

For overlapping 3x3 retain, where feasible:

- pattern-frequency KL;
- pattern-edge-frequency KL;
- decoded tile-frequency KL;
- decoded tile-edge-frequency KL.

# 12. POOLED RESULTS ARE NOT ENOUGH

The paper pools statistics over 100 generated outputs. Preserve this measurement because it enables comparison with the paper.

However, pooling can conceal run-to-run variation.

Therefore retain:

1. the paper-compatible **pooled distribution/KL result**;
2. **per-run metric values**;
3. across-run summaries such as:
   - mean;
   - median;
   - standard deviation;
   - useful quantiles or confidence intervals where appropriate.

Save raw per-run data.

This lets us distinguish:

- a generator whose individual outputs resemble the source;
- a generator whose outputs differ strongly but happen to average to the source distribution.

# 13. LONG-RANGE LAG-r PAIR-FREQUENCY EXPERIMENT

The paper's tile frequency can be viewed as a lag-0 statistic and its edge frequency as a nearest-neighbor/lag-1 pair statistic.

Extend this to:

**lag-r pair frequency**

for:

`r ∈ {1, 2, 4, 8, 16, 32}`

for Zelda 1x1 and Zelda 3x3.

Compute horizontal and vertical displacement separately.

At `r=1`, the implementation should agree as closely as possible with the ordinary edge-frequency metric.

For each `r`, compare source and generated pair distributions using KL divergence or the explicitly documented equivalent convention used by the primary metric.

Initially use **100 outputs**, matching the main experiment.

If runtime makes that unreasonable, perform a pilot, report the measured cost, and recommend a reduced count. Do not silently reduce it.

Produce:

- KL(r) horizontal curves;
- KL(r) vertical curves;
- pooled results;
- per-run distributions/spread where meaningful.

This experiment is intended to quantify whether apparent large-scale resemblance persists beyond immediate adjacency.

# 14. CONTRADICTIONS / BLANK CELLS

Do not silently omit contradiction or blank cells from structural analysis.

If an algorithm produces explicit contradiction/blank cells, treat them as an explicit category when calculating multi-lag statistics unless there is a compelling methodological reason not to.

If another treatment is used, document it.

Spatially clustered failure must not disappear from the metric merely because blank cells were dropped.

# 15. SELECTION ORDER AND ANISOTROPY

The Better Resemblance paper's experiments use a lexical/top-left-to-bottom-right selection order.

This may make the available context systematically asymmetric: upper/left neighbors are more likely already decided while lower/right neighbors are more likely `UNK`.

Therefore:

1. record the location-selection heuristic used for every experiment;
2. reproduce the paper's lexical behavior when attempting paper replication;
3. do not conflate a selection-order difference with a decision-heuristic difference;
4. preserve horizontal and vertical lag-r measurements separately.

After the principal replication/comparison is working, consider a secondary experiment comparing lexical selection against another controlled selection strategy to determine whether context-sensitive generation introduces measurable directional anisotropy.

Do not let this secondary experiment delay the core WFC-vs-SAT study.

# 16. FOURIER / SPECTRAL ANALYSIS: LATER, NOT FIRST

Do **not** perform a Fourier transform directly on integer tile IDs.

Tile IDs are categorical labels, not numerical magnitudes. Renumbering tile IDs must not change the structural metric.

If spectral analysis is implemented later, use a principled categorical representation such as binary indicator fields:

`f_t(x,y) = 1`

where tile type `t` occurs, and 0 elsewhere.

Possible later measurements include:

- 2D power spectra;
- radially averaged power spectral density;
- cross-spectra;
- anisotropy within frequency annuli;
- output/source spectral ratios.

If analyzing rendered imagery instead, label that explicitly as a **visual/perceptual texture measurement**, because it mixes combinatorial structure with tile artwork.

The lag-r real-space experiment is the priority.

Only implement Fourier/spectral analysis after the primary experiments are functioning or if I explicitly request it.

# 17. PLAIN SAT BASELINE

First determine whether Plain SAT/CDCL is deterministic in the current configuration.

If repeated executions produce the same satisfying assignment:

- report that;
- preserve deterministic Plain SAT as the actual baseline;
- one solution may characterize its output distribution;
- repeated executions may still be used for runtime/memory measurement.

Do not artificially randomize Plain SAT merely to obtain 100 different pictures.

A later condition may explicitly investigate:

`Randomized SAT`

using a defensible solver randomization mechanism.

Possible mechanisms might include solver phase randomization, decision-order randomization, controlled variable permutation, or another supported mechanism.

But it must remain a separate experimental condition.

Do not call variable-renumbered SAT "Plain SAT."

# 18. RUNTIME AND MEMORY

For applicable conditions measure:

- mean runtime;
- median runtime;
- runtime spread;
- peak memory.

Where possible separate:

- input/pattern preprocessing;
- context-frequency preprocessing;
- CNF construction;
- SAT solving;
- observer/plugin overhead;
- total wall-clock time.

For memory, state exactly what is measured.

Prefer a well-defined system measurement such as peak process RSS.

If subprocesses are involved, ensure the methodology captures them appropriately or explicitly state its limitations.

The research question is:

**For comparable WFC-style heuristics, what computational cost is introduced or removed by expressing the search through the SAT engine?**

# 19. EXISTING WFC-TO-SAT BENCHMARK SUITE

Only after Stick and Zelda validation should the new methods be applied to the existing repository benchmarks.

At present these are documented as:

- simple-knot
- cat
- chess
- knot
- simple-maze
- simple-wall.

Verify the actual checked-out repository before running them.

Preserve the previous benchmark configuration so old and new results can be compared.

Where scientifically useful, run both the existing configuration and the new 20x20 paper-style configuration, but label them clearly rather than mixing them.

# 20. ONE-COMMAND EXPERIMENT SCRIPT

Create a new shell-script entry point for this experiment rather than destructively replacing the existing one.

Prefer a descriptive name such as:

`run_context_sensitive_experiments.sh`

It should eventually:

- create output directories;
- run requested engines/heuristics;
- use reproducible seeds where applicable;
- record configurations;
- save raw per-run results;
- save summary CSV/JSON;
- save representative generated images;
- produce tables;
- produce lag-r plots;
- record failures;
- distinguish WFC/SAT/plugin conditions clearly;
- distinguish 1x1 and 3x3 clearly.

Make long experiments resumable where practical.

If 73 of 100 valid runs already exist, restarting should preferably continue with the remaining runs rather than overwrite the first 73.

Correctness takes priority over resumability.

# 21. REPRODUCIBILITY METADATA

Record at least:

- repository;
- Git branch;
- baseline commit hash;
- experiment commit hash;
- input;
- pattern size;
- output dimensions;
- engine;
- location-selection heuristic;
- decision heuristic;
- random seed;
- SAT solver/version/configuration;
- contradiction policy;
- backtracking policy;
- boundary/wrapping policy;
- number of runs;
- relevant dependency versions;
- experiment identifier/timestamp.

# 22. OUTPUT TABLES

Ultimately produce a resemblance table along the lines of:

| ExampleHeuristicWFC tile/pattern KLSAT tile/pattern KLWFC edge KLSAT edge KL |
| ---------------------------------------------------------------------------- |

and a performance table such as:

\| Example | Heuristic | WFC peak memory | SAT peak memory | WFC avg runtime | SAT avg runtime |
\|---|---|---:|---:|---:|

Refine these if the experiment reveals a more scientifically accurate representation.

Do not force Plain SAT into a WFC comparison where no corresponding WFC condition exists.

Use `N/A`.

Retain raw measurements behind every aggregate.

# 23. AUTOMATED CORRECTNESS TESTS

For a small input such as Stick, verify manually and programmatically:

- source tile frequencies;
- complete contexts;
- masked/UNK contexts;
- `freq(x,c)` counts;
- candidate weights;
- normalization;
- unseen-context fallback;
- deterministic behavior under controlled seeds;
- SAT state restoration after backtracking.

For the SAT plugin specifically test context state across:

- decisions;
- propagation;
- conflicts;
- undo;
- backtracking.

# 24. COMMIT IN SMALL MILESTONES

Once working on the new branch, make descriptive commits approximately corresponding to:

1. context-frequency preprocessing;
2. ordinary-WFC context-sensitive support;
3. SAT-plugin context-sensitive support;
4. correctness tests;
5. paper-compatible resemblance metrics;
6. experiment runner;
7. lag-r metrics;
8. runtime/memory measurement;
9. benchmark automation;
10. documentation/final cleanup.

Do not merge into the baseline branch.

# 25. WORK SEQUENCE

Proceed incrementally.

## Phase 0 — Establish and Protect the Baseline

Inspect repository, branches, status, and history.

Determine the correct baseline commit.

If anything is ambiguous or uncommitted, stop and report it.

Otherwise create `context-sensitive-experiments` from the verified baseline.

## Phase 1 — Architecture Inspection

Explain the existing WFC, SAT, observer/plugin, benchmark, and trace architecture.

## Phase 2 — Experimental Mapping

Map the Better Resemblance definitions precisely onto the existing implementation.

Identify semantic mismatches before coding.

## Phase 3 — Context-Frequency Preprocessing

Implement and hand-check `freq(x,c)` on a tiny example.

Test and commit.

## Phase 4 — Ordinary WFC Context-Sensitive Decision Heuristic

Implement, test, and commit.

## Phase 5 — SAT-Plugin Context-Sensitive Decision Heuristic

Implement with correct undo/backtracking behavior.

Test and commit.

## Phase 6 — WFC-vs-SAT Equivalence Validation

Use Stick first.

Compare uniform, frequency-weighted, and context-sensitive pairs.

## Phase 7 — Better Resemblance Replication

Attempt to reproduce the paper's Stick, Zelda 1x1, and Zelda 3x3 WFC measurements.

Investigate substantial discrepancies.

## Phase 8 — Main WFC/SAT Experiment

Run the controlled 100-run 20x20 comparison.

## Phase 9 — Lag-r Experiment

Compute and plot r = 1, 2, 4, 8, 16, 32 horizontal/vertical pair-frequency KL.

## Phase 10 — Runtime and Memory

Run controlled performance comparisons.

## Phase 11 — Existing Repository Benchmarks

Apply the validated framework to simple-knot, cat, chess, knot, simple-maze, and simple-wall.

## Phase 12 — Reproducible Shell Driver

Finalize the new one-command, preferably resumable workflow.

## Phase 13 — Documentation

Document methods, commands, output locations, known differences, limitations, and results.

# 26. WHAT TO DO RIGHT NOW

Do **not** start by implementing the entire experiment.

First inspect:

[https://github.com/stevex24/wfc-to-sat](https://github.com/stevex24/wfc-to-sat)

and the attached *Better Resemblance without Bigger Patterns* paper.

Then report:

1. current Git branch;
2. local and remote branches;
3. working-tree status;
4. staged/unstaged/untracked files;
5. recent relevant commits;
6. which commit/branch appears to be the correct baseline;
7. whether `context-sensitive-experiments` already exists;
8. existing ordinary-WFC implementation files/functions;
9. existing SAT/CDCL files/functions;
10. observer/plugin files/functions;
11. existing selection and decision heuristics;
12. existing tests;
13. existing benchmark scripts;
14. existing benchmark images;
15. which requested experimental conditions already exist;
16. important semantic differences between ordinary WFC and WFC-as-SAT;
17. files you expect will need modification;
18. files/scripts you expect to add;
19. the smallest sensible first implementation step.

If the baseline is unambiguously established and clean, create:

`context-sensitive-experiments`

from that baseline before modifying code.

If the baseline is ambiguous or contains work that might be lost, **stop and ask me rather than guessing**.

After the branch is safely established, proceed one small, tested phase at a time.