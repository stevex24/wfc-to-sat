# L-shaped, soft-match decision heuristic for callback-driven SAT WFC

## Background

This extends an existing re-implementation of Bateni, Karth & Smith, *Better Resemblance without Bigger Patterns* (FDG 2023), built on a SAT solver whose variable/value decisions are made by callbacks rather than the solver's own branching. That paper replaces Gumin's tile-frequency decision heuristic with a context-sensitive one: sample tile `x` at a location with weight `freq(x, c)`, where `c` is the tuple of the four cardinal neighbors (undecided or out-of-bounds neighbors marked `UNK`), falling back to `freq(x)` when the exact context never occurs in the source.

Two changes are requested here, drawn from example-based texture synthesis (Wei & Levoy 2000; Efros & Leung 1999):

1. **L-shaped causal context.** Under scanline (row-major) selection, the neighbors that are always decided are up-left, up, up-right, and left. Use exactly these four as the context instead of the cardinal four. This means the context is never `UNK` except at output borders.
2. **Soft matching instead of exact matching.** Instead of requiring the output context to equal a source context exactly, score every source location by how *similar* its L-context is to the query, and weight its center tile accordingly. No fallback is needed: every legal tile appears in the source at least once, so every legal tile always receives nonzero weight.

Everything else (SAT encoding, adjacency constraints, exactly-one constraints, propagation) is unchanged. Only the decision callback changes.

## Definitions

- `L(loc) = (UL, U, UR, LEFT)` — the four tiles at offsets `(-1,-1), (-1,0), (-1,+1), (0,-1)` relative to `loc`. Out-of-bounds positions are `UNK`. In the output, read these from the solver's current assignment; under scanline selection they are decided, but if propagation has not yet forced one, treat it as `UNK`.
- `S` — the source image. Precompute, for every source location `s`, its L-context `L_S(s)` and center tile `t(s)`. Do **not** wrap the source; out-of-bounds is `UNK`. Do not apply rotation/reflection augmentation in the first version (the L-shape is orientation-specific).
- `tile_dist(a, b)` — a distance between two tiles, with `tile_dist(a, a) = 0`. Provide two implementations behind one interface:
  - **Hamming** (baseline): `0` if `a == b`, else `1`.
  - **Pixel** (Wei–Levoy-style): mean squared RGB difference between the two tile bitmaps, normalized to `[0, 1]`. Precompute as a matrix over all tile ids.
  - `UNK` vs anything: distance `0.5` (or make this a parameter).
- `w = (w_UL, w_U, w_UR, w_L)` — per-position weights, default `(0.5, 1.0, 0.5, 1.0)`. Cardinal neighbors are also enforced by the adjacency constraints and carry more information; diagonals are *not* constrained by WFC at all, so they add information the solver never sees.
- `ctx_dist(q, c) = Σ_i w_i · tile_dist(q_i, c_i)` — weighted distance between two L-contexts.

## Decision callback

At each decision point:

1. **Select** `loc` = first unassigned output location in row-major order.
2. **Candidates** = tiles whose variable at `loc` is not currently assigned false (i.e., still legal after propagation).
3. **Query context** `q = L(loc)` from the current assignment.
4. **Score source locations.** For each source location `s` with `t(s) ∈ Candidates`, compute `d_s = ctx_dist(q, L_S(s))`.
5. **Aggregate to tile weights** (choose one; implement both):
   - **Softmax (recommended default):** `weight(x) = Σ_{s : t(s)=x} exp(−d_s / τ)`. Temperature `τ` is a parameter; default `0.1`.
   - **Efros–Leung threshold:** let `d_min = min_s d_s`; keep `{ s : d_s ≤ (1+ε) · d_min }` with `ε = 0.1`; `weight(x)` = number of kept `s` with `t(s) = x`.
6. **Sample** `x` from `weight` (normalized), using a seeded RNG, and return the literal `var(loc, x) = true`.

Notes:
- As `τ → 0` with Hamming distance, softmax weights converge to counts of exact L-context matches, i.e., the paper's heuristic on an L-shaped context. Keep an explicit `exact` mode too so this baseline is easy to run.
- The callback must be stateless with respect to the output: on conflict/backtrack the solver may re-query the same location with a smaller candidate set. Recompute from the current assignment each time.
- Vectorize step 4: store source contexts as an `(N_source, 4)` int array and `tile_dist` as a `(T+1, T+1)` matrix (row/col `T` = `UNK`); `d = Σ_i w_i · D[q_i, S[:, i]]` is one gather per position. Cost per decision is `O(N_source)`; for the Zelda map (~22k tiles) this is negligible.

## Parameters to expose

`tile_dist ∈ {hamming, pixel}`, `τ`, `ε`, `w`, `unk_dist`, aggregation `∈ {softmax, threshold, exact}`, RNG seed.

## Evaluation

Reuse the existing pipeline: stick example and Zelda overworld, 100 outputs of 20×20, plus a few 100×100 for inspection. Report tile-frequency KL and edge-frequency KL as in Table 1 of the paper, and the expressive-range scatter from Section 7.

Compare these decision heuristics:
1. Uniform
2. Tile frequency (Gumin)
3. Cardinal context, exact match (existing implementation)
4. L-context, exact match
5. L-context, softmax, Hamming
6. L-context, softmax, pixel

Add one metric the paper does not have: **largest copied patch** — the largest rectangular region of an output that appears verbatim in the source. Soft matching with a small `τ` should increase resemblance but may also increase copying; this metric shows whether it does. Sweep `τ ∈ {0.02, 0.1, 0.5, 2.0}` for heuristic 5 and plot KL and largest-copied-patch against `τ`.

Expected outcomes to sanity-check: heuristic 4 should match or beat heuristic 3 on the edge-frequency KL; heuristic 5 at small `τ` should be close to heuristic 4; on the stick example, all L-context variants should produce continuous vertical lines.
