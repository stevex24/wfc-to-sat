# Zelda object preprocessing prototype

The prototype follows a deliberately human-in-the-loop pipeline:

`automatic candidate discovery -> human semantic selection -> object/region-aware constraints -> WFC/SAT generation`

`object_preprocessor.discover` deterministically nominates repeated 2×2–3×3 patches and bounded connected components, ranks them by mechanism, tile diversity, repetition, and size, and suppresses contained duplicates. It does not infer semantic meaning from pixels. A person edits `selections.json` and chooses `ignore`, `texture`, `object`, or `region`.

An object selection records relative tile offsets plus a one-tile boundary ring from the selected source occurrence. `constrain` turns those requirements into unit clauses over the existing 1×1 SAT placement variables. Texture selections add no clauses; region selections preserve only their perimeter. This is intentionally a small integration layer over the existing weighted Zelda model.

The same blue rectangle can therefore be treated as texture or as a meaningful region (such as a football field) according to the human decision; geometry alone does not determine semantics.
