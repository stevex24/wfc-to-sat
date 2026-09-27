# Claude Code Task: CDCL Search Visualizer for SAT-Based Tile Placement

## Context

We have a compiler that takes pattern tiles plus adjacency constraints and emits DIMACS
CNF describing valid tile placements on a W×H grid. Variables use a one-hot encoding:
one Boolean per (x, y, pattern) triple, meaning "pattern P is placed at cell (x, y)",
with exactly-one constraints per cell and adjacency clauses between neighbors.

We want to build an animated visualization of the SAT solver actually solving this —
the SAT analogue of Wave Function Collapse's well-known step-by-step generation
animations.

## Critical design constraint (read this before writing code)

A naive visualization that renders only positive assignments will look nothing like WFC
and will be unwatchable. Four reasons, all of which the architecture must address:

1. **~99% of assignments are negative.** On a 32×32 grid with 100 patterns there are
   ~102,400 variables and only 1,024 true in the final model. Negative literals are the
   bulk of the signal and must be used, not discarded.
2. **CDCL decisions are not spatially local.** VSIDS/VMTF pick by conflict activity, not
   grid adjacency, so raw decisions scatter across the map.
3. **Backjumping is non-chronological.** One conflict can undo thousands of assignments.
4. **Restarts backtrack to level 0**, repeatedly blanking the grid.

The two mitigations below are requirements, not optional polish.

### Mitigation A: render the domain, not the assignment

For each cell, track the set of patterns *not yet falsified*. That set is precisely WFC's
entropy. Negative literals shrink it. Render it. Support at least two view modes:

- **Entropy heatmap** — color each cell by |domain|, hot = many options remaining.
- **Superposition blend** — composite the still-possible patterns' pixels, weighted by
  pattern frequency, so cells appear blurry and sharpen as they collapse. This is the
  classic WFC aesthetic and it falls directly out of the negative literals.

A cell is "collapsed" when it receives a positive literal or its domain reaches size 1.

### Mitigation B: WFC-style decision heuristic via `cb_decide`

Implement `decide()` to mimic WFC's collapse rule: select the uncollapsed cell with the
smallest domain (minimum remaining values / lowest entropy), then choose a pattern from
that domain weighted by pattern frequency, and return the corresponding positive literal.
Return 0 to defer to the solver's own heuristic.

Make this **toggleable via CLI flag** (`--heuristic={wfc,solver}`) — comparing the two
side by side is a primary deliverable of this project, not an afterthought.

## Technical target

**Primary stack:** Python + PySAT (`python-sat`), solver class `Cadical195` (or
`Cadical300`). PySAT's IPASIR-UP support is exposed through `pysat.engines.Propagator`.
The relevant methods and their exact signatures:

```python
class Propagator:
    def on_assignment(self, lit: int, fixed: bool = False) -> None: ...
    def on_new_level(self) -> None: ...
    def on_backtrack(self, to: int) -> None: ...
    def check_model(self, model: list[int]) -> bool: ...
    def decide(self) -> int: ...            # 0 = no suggestion
    def propagate(self) -> list[int]: ...   # [] = nothing to propagate
    def provide_reason(self, lit: int) -> list[int]: ...
```

Attach with `solver.connect_propagator(prop)`, then register each placement variable
with the solver's observe call. **Only observe the (x, y, pattern) placement variables.**
Do not observe auxiliary variables from the at-most-one encoding — they carry no visual
meaning and observing them costs performance.

Verify the exact PySAT method names for connecting and observing against the installed
version before building on them; the API has changed across releases. If PySAT's
propagator support is missing or broken in the installed version, fall back to the
`cadical_py` binding (https://github.com/manfredscheucher/cadical_py) or a direct C++
CaDiCaL `ExternalPropagator` subclass. Note that CaDiCaL 2.0+ **batches** assignment
notification: the C++ signature is `notify_assignment(const std::vector<int>& lits)`,
with no `is_fixed` flag. Older tutorials showing `(int lit, bool is_fixed)` are outdated.

## Architecture: log then replay

Do **not** couple the solver directly to a live renderer. The solver emits millions of
events per second; a live render will either stall the solve or drop frames. Instead:

**Stage 1 — Instrumented solve (`solve_trace.py`)**
Runs the solver with the observer propagator attached, writes a compact binary or
JSONL event trace to disk. Event types:

- `ASSIGN_POS(x, y, pattern, level)` — cell collapsed
- `ASSIGN_NEG(x, y, pattern, level, remaining)` — domain refined
- `LEVEL_PUSH(level)`
- `BACKJUMP(to_level, count_undone)`
- `RESTART` (detectable as a backjump to level 0)
- `CONFLICT(clause_cells)` — if learned-clause info is accessible, record which cells
  appear in the learned clause; this makes a great visual highlight
- `MODEL_FOUND`

Include a header record with W, H, pattern count, pattern→pixel-data table, and the
variable-index mapping, so the player is fully self-contained.

**Stage 2 — Player (`play_trace.py` or a web player)**
Reads the trace and renders. Requirements:

- Play / pause / step-forward / step-backward / scrub-to-position
- Adjustable playback rate, including "N events per frame" for fast-forwarding
- View mode switch: collapsed-tiles-only, entropy heatmap, superposition blend
- Decision-level indicator and a live conflict counter
- Visual emphasis on backjumps — e.g. a brief flash or shockwave over the affected
  cells, scaled by how many assignments were undone
- Export to PNG frame sequence and/or MP4/GIF

Rendering backend: your call, but prefer something that makes video export easy.
A small HTML/JS canvas player fed by a JSON trace is a reasonable choice and makes the
result shareable; pygame is fine if simpler.

## State management gotcha

**The solver does not restore propagator state on backtrack.** The observer must
maintain its own undo trail keyed by decision level, and on `on_backtrack(to)` unwind
every level above `to`, restoring each cell's domain. Get this right early and test it
in isolation — a corrupted domain model will silently produce a plausible-looking but
wrong animation, which is the worst failure mode here.

Also note that assignment notification is not guaranteed to be eager: notifications
arrive in batches at propagation boundaries. The trace is still correctly ordered, but
do not assume one notification per solver step.

## Solver tuning for watchability

Expose CaDiCaL option passthrough (PySAT's `Cadical195.configure()`; option list at
`https://github.com/arminbiere/cadical/blob/master/src/options.hpp`). In particular,
allow raising the restart interval — default restart behavior blanks the grid constantly
and makes the animation hard to follow. Document which options produce good animations.

Be aware that observing variables freezes them, disabling bounded variable elimination.
This is expected and acceptable; note the solve-time cost in the README.

## Deliverables

1. `observer.py` — the `Propagator` subclass: domain tracking, undo trail, event emission
2. `solve_trace.py` — CLI: takes DIMACS + a variable-mapping sidecar file, emits a trace
3. `play_trace.py` (or web player) — the replay UI
4. `README.md` — usage, trace format spec, tuning notes, and a short section on what the
   two heuristic modes look like and why they differ
5. A small end-to-end example: a hand-written 8×8 instance with ~6 patterns, checked in,
   so the pipeline is runnable immediately without the full compiler

## Testing

- Unit test the undo trail: drive `on_assignment` / `on_new_level` / `on_backtrack`
  synthetically and assert domains return to prior states exactly.
- Assert that every trace ends in a state where each cell's domain has size 1 and the
  resulting tilemap satisfies all adjacency constraints.
- Test on a deliberately UNSAT instance and confirm the player handles termination
  without a model.

## Style

Small, testable modules. Type hints. No heavyweight framework. The trace format should
be documented well enough that someone could write an alternative player against it.
Prefer clarity over cleverness — this is partly a pedagogical artifact.
