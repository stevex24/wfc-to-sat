# Section 8 inspection findings

Inspected asset: Kenney Tiny Town, 132 separate 16×16 PNG tiles (CC0), downloaded from
the URL recorded in `manifest.json`.

1. **Roof overhang:** the roof end tiles and body end tiles occupy the same tile columns.
   Decorative pixels differ inside a tile, but there is no extra tile-cell overhang.
   The experiment therefore uses one `In(x,y)` family.
2. **House separation:** the pack contains only artwork, not adjacency metadata. End-tile
   artwork visually terminates a row, but the generic repository compiler cannot infer a
   non-house gap from pixels. The house grammar explicitly permits ground—not another
   left-end—after a right-end and forbids body-to-top vertical contact. Distinct houses
   consequently have at least one non-house cell between them.
3. **Vertical invariant:** with that separation and the vertical roof/body grammar,
   vertically adjacent `In` cells necessarily belong to the same house. This is the
   invariant required by the four-cell equal-width clauses.

The selected IDs and their semantic roles are data in `manifest.json`; none are
hardcoded in the compiler.
